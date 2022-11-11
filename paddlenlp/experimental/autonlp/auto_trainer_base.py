import datetime
from abc import ABCMeta, abstractmethod
from pickle import NONE
from paddlenlp.trainer.trainer_utils import EvalPrediction
from ray import tune
from ray.tune.result_grid import ResultGrid
from typing import Callable, Dict, Any, Union, Optional
import copy
from paddle.io import Dataset
from paddlenlp.transformers import PretrainedFasterTokenizer, PretrainedTokenizer
from paddlenlp.trainer import TrainingArguments, CompressionArguments


class AutoTrainerBase(metaclass=ABCMeta):
    
    def __init__(self, metric_for_best_model: str =None, preset: str=None, language="Chinese", **kwargs):
        self.metric_for_best_model = metric_for_best_model
        self.preset = preset
        self.language = language

    @property
    @abstractmethod
    def _default_training_argument(self) -> TrainingArguments:
        pass

    @property
    @abstractmethod
    def _default_compress_argument(self) -> CompressionArguments:
        pass

    @property
    @abstractmethod
    def _model_candidates(self) -> Dict[str, Any]: 
        pass
    
    @abstractmethod
    def _data_checks_and_inference(self, train_dataset: Dataset, eval_dataset: Dataset):
        pass

    @abstractmethod
    def _construct_trainable(self, train_dataset: Dataset, eval_dataset: Dataset) -> Callable:
        pass
    
    @abstractmethod
    def _compute_metrics(self, eval_preds: EvalPrediction) -> Dict[str, float]:
        pass
    
    @abstractmethod
    def _preprocess_fn(self,
        example: Dict[str, Any],
        tokenizer: Union[PretrainedTokenizer, PretrainedFasterTokenizer], max_seq_length: int, is_test: bool = False) -> Dataset:
        pass

    def _override_arguments(self, config: Dict[str, Any], default_arguments: TrainingArguments) -> Any:
        new_arguments = copy.deepcopy(default_arguments)
        for key, value in config.items():
            if key.startswith(default_arguments.__class__.__name__):
                _, hp_key = key.split(".")
                setattr(new_arguments, hp_key, value)
        return new_arguments
    
    def _override_training_arguments(self, config: Dict[str, Any]) -> TrainingArguments:
        return self._override_arguments(config, self._default_training_argument)

    def _override_compression_arguments(self, config: Dict[str, Any]) -> CompressionArguments:
        return self._override_arguments(config, self._default_compress_argument)
        
    def train(self,
        train_dataset: Dataset,
        eval_dataset: Dataset,
        num_models: int =1,
        num_gpus: Optional[int] =None,
        num_cpus: Optional[int] =None,
        max_concurrent_trials: Optional[int]=None,
        time_budget_s: Optional[Union[int, float, datetime.timedelta]] = None
        ) -> ResultGrid:
        self._data_checks_and_inference(train_dataset, eval_dataset)
        trainable = self._construct_trainable(train_dataset, eval_dataset)
        if num_gpus or num_cpus:
            hardware_resources = {}
            if num_gpus:
                hardware_resources["gpu"] = num_gpus
            if num_cpus:
                hardware_resources["cpu"] = num_cpus
            trainable = tune.with_resources(trainable, hardware_resources)
        tune_config = tune.tune_config.TuneConfig(
            num_samples=num_models,
            time_budget_s=time_budget_s,
            max_concurrent_trials=max_concurrent_trials)
        tuner = tune.Tuner(
            trainable,
            param_space=self._model_candidates[self.preset],
            tune_config=tune_config)
        self.training_results = tuner.fit()
        return self.training_results