import glob
import sys

import torch

sys.path.append('../')
import argparse

from model.dataloader import get_data_bundle
from model.model import CoNTGenerator
from model.callback import MLECallback, CoNTCallback
from fastNLP import Trainer
from fastNLP import prepare_dataloader
from model.optimizer import Adafactor
from model.metrics import CoNTValidMetric

DATASET = "rsum"
WARM_UP_PATH = "results/2023-03-27-11_17_48_518372/epoch-39_step-1640.pt"

def str2bool(v):
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def train_model(args):
    if args.warmup:
        print("=" * 10, " Warmup with MLE ...", "=" * 10)
        callbacks = [MLECallback(args, metric="torch_ngram#ngram-overlap")]
    else:
        print("=" * 10, "Contrastive learning based training...", "=" * 10)
        callbacks = [CoNTCallback(args, metric="torch_ngram#ngram-overlap", topk=3)]

    valid_metric = CoNTValidMetric()
    data_bundle = get_data_bundle(args)
    if not args.warmup:
        model = torch.load(WARM_UP_PATH).to("cuda:0")
        print('加载',WARM_UP_PATH)

    else:
        model = CoNTGenerator(args.PTM, args.model_name, args.pad_id, args).to("cuda:0")
        print("初始化加载pretrained_weights/xsum/t5")
    optimizer = Adafactor(
        model.parameters(),
        lr=args.lr,
        relative_step=False,
        scale_parameter=False,
        warmup_init=False,
    )
    if not args.reset_optimizer:
        optim_pt = torch.load(WARM_UP_PATH + "model.optm")
        optimizer.load_state_dict(optim_pt)
        print("=" * 20, "load optimizer from", args.model_name + ".optm")

    dls = prepare_dataloader(data_bundle, batch_size=args.batch_size)
    for dl in dls.values():
        dl.set_pad('src_inp', pad_val=args.pad_id)
        dl.set_pad('target_inp', pad_val=args.pad_id)
        dl.set_pad('target_outp', pad_val=args.ignore_index)
    devices = list(map(int, args.gpus.split(",")))
    trainer = Trainer(model=model, train_dataloader=dls['train'], optimizers=optimizer,
                      accumulation_steps=args.accum_count,
                      evaluate_dataloaders=dls['val'], metrics={"ngram-overlap": valid_metric}, device=devices,
                      driver="torch", n_epochs=args.n_epochs, callbacks=callbacks, fp16=False, evaluate_every=max(1,args.validate_every),
                      torch_kwargs={'ddp_kwargs': {'find_unused_parameters': True}})
    file = open('results/used_for_ChatGPT.txt', mode='a')#本次训练保存
    file.write("store the sentence for ChatGPT")
    file.write('\n')
    trainer.run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='training/testing of CoNT'
    )

    parser.add_argument('--save_path', default="results/",
                        help='root of the model', type=str)
    parser.add_argument('--gpus', default="0,1",
                        help='available gpus for training(separated by commas)', type=str)
    parser.add_argument('--batch_size', default=16,
                        help='the training batch size', type=int)
    parser.add_argument('--accum_count', default=1,
                        help='number of updates steps to accumulate before performing a backward/update pass', type=int)
    parser.add_argument('--lr', default=1e-4, type=float)
    parser.add_argument('--n_epochs', default=40,
                        help='total number of training epochs', type=int)

    parser.add_argument('--max_sample_num', default=16, type=int)
    parser.add_argument('--n_gram', default=2, type=int)
    parser.add_argument('--dataset', default="rsum")

    parser.add_argument('--mode', default='t5-small', choices=["train", "test", "val"])
    parser.add_argument('--warmup', type=str2bool, default=True,
                        help="if you set warmup=False ensure `WARM_UP_PATH` not empty")
    parser.add_argument('--model_name', default="t5-small", choices=["google/pegasus-xsum", "t5-small"])
    # parser.add_argument('--accum_count', default=1)
    parser.add_argument('--warmup_batch_size', default=16)

    parser.add_argument('--validate_every', default=40, type=int)
    # no need to set in training mode



    parser.add_argument('--PTM', default="t5")
    parser.add_argument('--reset_optimizer', type=str2bool, default=True)
    parser.add_argument('--scratch', type=str2bool, default=False)

    parser.add_argument('--max_src_len', default=784, type=int)
    parser.add_argument('--max_tgt_len', default=128, type=int)
    # inference parameters
    parser.add_argument('--min_length', default=0, type=int)
    parser.add_argument('--max_length', default=128, type=int)
    parser.add_argument('--beam_size', default=12, type=int)
    parser.add_argument('--early_stop', default=True, type=str2bool)
    parser.add_argument('--no_repeat_ngram', default=4, type=int)
    parser.add_argument('--alpha', default=0.5, type=float)
    parser.add_argument('--diversity_pen', default=2.0, type=float)
    parser.add_argument('--length_pen', default=0.8, type=float)

    # no need to set
    parser.add_argument('--pad_id', type=int)
    parser.add_argument('--eos_id', type=int)
    parser.add_argument('--bos_id', default=None, type=int)
    parser.add_argument('--ignore_index', default=-100, type=int)
    args = parser.parse_known_args()[0]

    train_model(args)
