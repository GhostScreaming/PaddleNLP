import functools
from paddlenlp.transformers import PretrainedFasterTokenizer, PretrainedTokenizer
from paddlenlp.trainer.trainer_utils import EvalPrediction
from ray import tune
from typing import Callable, Dict, Any
import paddle
from  paddle.metric import Accuracy
from paddlenlp.data import DataCollatorWithPadding
from paddlenlp.transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from paddlenlp.trainer import Trainer, TrainingArguments, CompressionArguments

from .auto_trainer_base import AutoTrainerBase

class AutoTrainerForTextClassification(AutoTrainerBase):
    def __init__(self,
        text_column: str,
        label_column: str,
        # TODO: support problem_type
        **kwargs
        ):
        super(AutoTrainerForTextClassification, self).__init__(**kwargs)
        self.text_column = text_column
        self.label_column = label_column

    @property
    def _default_training_argument(self) -> TrainingArguments:
        return TrainingArguments(
            output_dir="trained_model",
            num_train_epochs=1,
            learning_rate=1e-5,
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            disable_tqdm=True,
            metric_for_best_model="accuracy",
            load_best_model_at_end=True,
            evaluation_strategy="epoch",
            save_strategy="epoch")

    @property
    def _default_compress_argument(self) -> CompressionArguments:
        return CompressionArguments(
            width_mult_list=['3/4'],
            per_device_train_batch_size=8,
            per_device_eval_batch_size=8,
            num_train_epochs=1,
            output_dir="pruned_model"
            )


    @property
    def _model_candidates(self) -> Dict[str, Any]: 
        return {
            "test": {
                "PreprocessArguments.max_seq_length": 128,
                "TrainingArguments.per_device_train_batch_size": 2,
                "TrainingArguments.per_device_eval_batch_size": 2,
                "TrainingArguments.max_steps": 5,
                "TrainingArguments.model_name_or_path": "ernie-3.0-nano-zh",
                "TrainingArguments.learning_rate": tune.choice([5e-5, 1e-5])
            },
        }
    
    def _data_checks_and_inference(self, train_dataset: Dataset, eval_dataset: Dataset):
        # TODO: support label ids that is already encoded
        train_labels = {i[self.label_column] for i in train_dataset}
        dev_labels = {i[self.label_column] for i in eval_dataset}
        self.id2label = list(train_labels.union(dev_labels))
        self.label2id = { label: i for i, label in enumerate(self.id2label) }
        
    def _construct_trainable(self, train_dataset: Dataset, eval_dataset: Dataset) -> Callable:
        def trainable(config):
            model_path = config["TrainingArguments.model_name_or_path"]
            max_seq_length = config["PreprocessArguments.max_seq_length"]
            tokenizer = AutoTokenizer.from_pretrained(model_path)
            trans_func = functools.partial(
                self._preprocess_fn,
                tokenizer=tokenizer,
                max_seq_length=max_seq_length,
            )
            processed_train_dataset = train_dataset.map(trans_func, lazy=False)
            processed_eval_dataset = eval_dataset.map(trans_func, lazy=False)

            # define model
            model = AutoModelForSequenceClassification.from_pretrained(
                model_path,
                num_classes=len(self.id2label))
            training_args = self._override_training_arguments(config)
            trainer = Trainer(
                model=model,
                tokenizer=tokenizer,
                args=training_args,
                criterion=paddle.nn.loss.CrossEntropyLoss(),
                train_dataset=processed_train_dataset,
                eval_dataset=processed_eval_dataset,
                data_collator=DataCollatorWithPadding(tokenizer),
                compute_metrics=self._compute_metrics,
            )
            trainer.train()
            trainer.save_model()
            eval_metrics = trainer.evaluate(eval_dataset)
            return eval_metrics
        return trainable

    
    def _compute_metrics(self, eval_preds: EvalPrediction) -> Dict[str, float]:
        metric = Accuracy()
        correct = metric.compute(
            paddle.to_tensor(eval_preds.predictions),
            paddle.to_tensor(eval_preds.label_ids),
        )
        metric.update(correct)
        acc = metric.accumulate()
        return {"accuracy": acc}

    
    def _preprocess_fn(self, example: Dict[str, Any],
        tokenizer: Union[PretrainedTokenizer, PretrainedFasterTokenizer], max_seq_length: int, is_test: bool = False):
        result = tokenizer(text=example[self.text_column], max_seq_len=max_seq_length)
        if not is_test:
            result["labels"] = paddle.to_tensor([self.label2id[example[self.label_column]]], dtype='int64')
        return result
