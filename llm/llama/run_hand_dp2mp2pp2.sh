# Copyright (c) 2023 PaddlePaddle Authors. All Rights Reserved.
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#     http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -x                                                                                                                   
unset CUDA_VISIBLE_DEVICES                                                                                               
                                                                                                                         
export FLAGS_call_stack_level=3                                                                                          
export FLAGS_use_cuda_managed_memory=true                                                                                
task_name="llama_auto_dp2mp2pp2"                                                                                         
rm -rf output/$task_name/                                                                                                
rm -rf "output/$task_name""_log"                                                                                         
                                                                                                                         
export SOT_LOG_LEVEL=4                                                                                                   
export PYTHONPATH=../../:$PYTHONPATH                                                                                     
#ulimit -c unlimited                                                                                                     
#export GLOG_v=10                                                                                                        
export CUDA_VISIBLE_DEVICES="0,1,2,3,4,5,6,7"                                                                            
export FLAGS_embedding_deterministic=1                                                                                   
export FLAGS_cudnn_deterministic=1                                                                                       
export NVIDIA_TF32_OVERRIDE=0

python -u  -m paddle.distributed.launch \
    --gpus "0,1,2,3,4,5,6,7" \
    --log_dir "hand_load" \
    run_pretrain.py \
    --model_type "llama" \
    --model_name_or_path "facebook/llama-7b" \
    --tokenizer_name_or_path "facebook/llama-7b" \
    --input_dir "./data" \
    --output_dir "output/$task_name" \
    --split 949,50,1 \
    --max_seq_length 2048 \
    --per_device_train_batch_size 1 \
    --gradient_accumulation_steps 2 \
    --per_device_eval_batch_size 2 \
    --use_flash_attention 0 \
    --use_fused_rms_norm 0 \
    --fp16 0 \
    --fp16_opt_level "O2"  \
    --scale_loss 1024 \
    --tensor_parallel_degree 2 \
    --pipeline_parallel_degree 2 \
    --virtual_pp_degree 1 \
    --sequence_parallel 0 \
    --learning_rate 0.00001 \
    --min_learning_rate 0.000001 \
    --max_steps 20000 \
    --save_steps 5000000 \
    --weight_decay 0.01 \
    --warmup_ratio 0.01 \
    --max_grad_norm 1.0 \
    --logging_steps 1 \
    --dataloader_num_workers 1 \
    --eval_steps 1000000 \
    --report_to "visualdl" \
    --disable_tqdm true \
    --continue_training 1 \
    --recompute 0 \
    --do_train \
    --do_eval \
    --device "gpu" \
    --distributed_dataloader 1
    # --pipeline_parallel_config "disable_partial_send_recv"  # if set sequence_parallel True, please note off this line.
    # reompute settings:
    # --no_recompute_layers 0 1 2 3 4 5 6 7 8 9 10 ... int int
    # --pp_recompute_interval 0 # A value of 0 indicates no recomputation.
