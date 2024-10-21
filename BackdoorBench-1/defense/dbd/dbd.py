'''
This file is modified based on the following source:
link : https://github.com/SCLBD/DBD
The defense method is called dbd.
The license is bellow the code

The update include:
    1. data preprocess and dataset setting
    2. model setting
    3. args and config
    4. save process
    5. new standard: robust accuracy
    6. add some new backdone such as mobilenet efficientnet and densenet, reconstruct the backbone of vgg and preactresnet              note: backdone是骨干网
    7. Different data augmentation (transform) methods are used
    8. rewrite the dateset
basic sturcture for defense method:
    1. basic setting: args
    2. attack result(model, train data, test data)
    3. dbd defense:
        a. self-supervised learning generates feature extractor
        b. learning model using extracted features
        c. the samples with poor confidence were excluded, and semi-supervised learning was used to continue the learning model
    4. test the result and get ASR, ACC, RA 
'''
# note: Poisoned samples will gather together in the feature space due to the standard supervised learning
# note: Input: a poisoned dataset; Output: secure model and clean data
# note: Defense strategy: poison detection and backdoor inhibition

import logging
import time
import argparse
import shutil
import sys
import os


sys.path.append('../')
sys.path.append(os.getcwd())
from defense.dbd.data.prefetch import PrefetchLoader


import numpy as np
import torch
import torch.nn as nn
import torch.distributed as dist # note: 分布式计算
import torch.multiprocessing as mp # note: 并行处理

import yaml # note: YAML 文件通常用于配置文件的存储

from pprint import pprint, pformat
from utils.aggregate_block.dataset_and_transform_generate import get_input_shape, get_num_classes, get_transform, get_transform_prefetch # note: get_transform是数据集的预处理转换流程
                                                                                                                                         # note: 在深度学习中，prefetch 参数通常与数据加载和预处理相关，它的主要作用是优化数据加载的性能，从而提高训练速度。
 
from data.utils import (
    get_loader, # note: 创建数据加载器
    get_semi_idx, # note: Get labeled and unlabeled index from semi-supervised learning.
)
from data.dataset import PoisonLabelDataset, SelfPoisonDataset, MixMatchDataset # note: Poison-Label dataset wrapper; 提供一个“毒化标签”数据集的封装, 返回一个包含图像、标签和其他相关信息的字典。这个字典随后可以在PyTorch的DataLoader中使用，以迭代方式获取批量数据用于训练或测试模型。
                                                                                # note: Self-supervised poison-label contrastive dataset; 
                                                                                # note: Semi-supervised MixMatch dataset.
from utils.aggregate_block.fix_random import fix_random # note: 固定随机数生成器的种子，以获得可重复的结果。
from utils.save_load_attack import load_attack_result
from utils_db.box import get_information # note: 设置一个带有毒药标签的数据集的训练环境
from model.model import SelfModel, LinearModel
from model.utils import (
    get_network_dbd, # note: 5个DNN模型
    load_state, # note: 从指定的检查点（checkpoint）加载训练状态
    get_criterion, # note: 损失函数选择
    get_optimizer, # note: 优化器: Adam, SGD
    get_scheduler, # note: 选择并返回一个适当的学习率调度器
)
from utils.bd_dataset import prepro_cls_DatasetBD, xy_iter # note: prepro_cls_DatasetBD: 用于处理包含后门攻击的数据集, 返回一个__________________________________???
                                                           # note: xy_iter: 创建PyTorch数据加载器
from utils_db.setup import (
    load_config,
)
from utils_db.trainer.log import result2csv
from utils_db.trainer.simclr import simclr_train # note: 这是一个典型的深度学习训练循环，包括了数据加载、前向传播、损失计算、反向传播和参数更新等步骤
from utils_db.trainer.semi import mixmatch_train # note: 这段代码实现了一个名为 MixMatch 的半监督学习算法的训练过程, MixMatch在Stage 3 
from utils_db.trainer.simclr import linear_test, poison_linear_record, poison_linear_train # note: __________________________________???

def get_args():
    # set the basic parameter
    parser = argparse.ArgumentParser()

    parser.add_argument('--device', type=str, help='cuda, cpu')
    parser.add_argument('--checkpoint_load', type=str)
    parser.add_argument('--checkpoint_save', type=str)
    parser.add_argument('--log', type=str)
    parser.add_argument("--data_root", type=str)

    parser.add_argument('--dataset', type=str, help='mnist, cifar10, gtsrb, celeba, tiny') 
    parser.add_argument("--num_classes", type=int)
    parser.add_argument("--input_height", type=int)
    parser.add_argument("--input_width", type=int)
    parser.add_argument("--input_channel", type=int)

    parser.add_argument('--epochs', type=int)
    parser.add_argument('--batch_size', type=int)
    parser.add_argument("--num_workers", type=float)
    parser.add_argument("--num_workers_semi", type=float)
    parser.add_argument('--lr', type=float)

    parser.add_argument('--attack', type=str)
    parser.add_argument('--poison_rate', type=float)
    parser.add_argument('--target_type', type=str, help='all2one, all2all, cleanLabel') 
    parser.add_argument('--target_label', type=int)
    parser.add_argument('--trigger_type', type=str, help='squareTrigger, gridTrigger, fourCornerTrigger, randomPixelTrigger, signalTrigger, trojanTrigger')

    parser.add_argument('--random_seed', type=int, help='random seed')
    parser.add_argument('--index', type=str, help='index of clean data')
    parser.add_argument('--model', type=str, help='resnet18')
    parser.add_argument('--result_file', type=str, help='the location of result')
    parser.add_argument('--yaml_path', type=str, default="./config/defense/dbd/config.yaml", help='the path of yaml')

    # set the parameter for the dbd defense
    parser.add_argument('--prefetch',type=bool )
    parser.add_argument('--epoch_warmup',type=int )
    parser.add_argument('--batch_size_self',type=int )
    parser.add_argument('--temperature',type=int )
    parser.add_argument('--epsilon',type=int )
    parser.add_argument('--epoch_self',type=int )


    arg = parser.parse_args()

    print(arg)
    return arg


def dbd(args,result):
    ### set logger
    logFormatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] [%(filename)s:%(lineno)d] %(message)s',
        datefmt='%Y-%m-%d:%H:%M:%S',
    )
    logger = logging.getLogger()
    if args.log is not None and args.log != '':
        fileHandler = logging.FileHandler(os.getcwd() + args.log + '/' + time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime()) + '.log')
    else:
        fileHandler = logging.FileHandler(os.getcwd() + './log' + '/' + time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime()) + '.log')
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)

    logger.setLevel(logging.INFO)
    logging.info(pformat(args.__dict__))

    fix_random(args.random_seed)

    logging.info("===Setup running===")

    if args.checkpoint_load == None:
        args.resume = 'False' 
    else :
        args.resume = args.checkpoint_load

    if args.dataset == 'cifar10':
        config_file = './defense/dbd/config_z/pretrain/' + 'squareTrigger/' + args.dataset + '/example.yaml'
    else:
        config_file = './defense/dbd/config_z/pretrain/' + 'squareTrigger/imagenet/example.yaml'
    config_ori, inner_dir, config_name = load_config(config_file)
    gpu = int(os.environ['CUDA_VISIBLE_DEVICES']) 
    logging.info("===Prepare data===")
    # args.model = 'resnet' # note: dbd原代码是resnet，backdoorbench作者采用resnet18
    information = get_information(args,result,config_ori) # note: Output: get_information(args,result,config_ori)返回一个包含训练数据加载器、模型、损失函数、优化器、学习率调度器和恢复的epoch数的字典。
                                                          # note: Input: asgs: 命令行参数解析对象; result: 攻击结果; config_ori: 从配置文件中加载的配置信息
                                                          # note: information: 设置一个带有毒药标签的数据集的训练环境
    self_poison_train_loader = information['self_poison_train_loader'] # note: 训练数据加载器
    self_model = information['self_model'] # note: 模型
    criterion = information['criterion'] # note: 损失函数
    optimizer = information['optimizer'] # note: 优化器
    scheduler = information['scheduler'] # note: 学习率调度器
    resumed_epoch = information['resumed_epoch'] # note: 恢复的epoch数

    # a.self-supervised learning generates feature extractor
    for epoch in range(args.epoch_self - resumed_epoch):
    
        # note: 一种无监督深度学习训练循环, 需要注意的是simclr_train函数不仅生成了一个新的模型，还输入了攻击代码中生成的毒数据集(也就是Input)
        # note: simclr_train不需要使用标签，所以是label-removed training
        self_train_result = simclr_train( 
            self_model, self_poison_train_loader, criterion, optimizer, logger, False
        )
        # note: 无监督训练结束, 下面代码说的是保存一些无监督训练的信息。
        if scheduler is not None:
            scheduler.step()
            logger.info(
                "Adjust learning rate to {}".format(optimizer.param_groups[0]["lr"])
            )


        result_self = {"self_train": self_train_result}

        saved_dict = {
            "epoch": epoch + resumed_epoch + 1,
            "result": result_self,
            "model_state_dict": self_model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
        }
        if scheduler is not None:
            saved_dict["scheduler_state_dict"] = scheduler.state_dict()

        ckpt_path = os.path.join(os.getcwd() + args.checkpoint_save, "self_latest_model.pt")
        torch.save(saved_dict, ckpt_path)
        logger.info("Save the latest model to {}".format(ckpt_path))
        # note: .pt是PyTorch 的默认模型文件格式，用于保存和加载完整的 PyTorch 模型，包含模型的结构和参数等信息。
        # note: 这里把自学习最新的模型给保存起来了，这里的模型就是feature extractor. 
        
    if args.dataset == 'cifar10':
        config_file_semi = './defense/dbd/config_z/semi/' + 'badnets/' + args.dataset + '/example.yaml'
    else:
        config_file_semi = './defense/dbd/config_z/semi/' + 'badnets/imagenet/example.yaml'

    # note: 下面开始对feature extractor进行finetune
    # note: 要想微调就不能用后门攻击后的结果了(后门攻击后的结果用来自学习feature extractor), 得自己产生bad dataset, clean dataset就是那4个数据集，这里用的是cifar10
    finetune_config, finetune_inner_dir, finetune_config_name = load_config(config_file_semi)
    pretrain_config, pretrain_inner_dir, pretrain_config_name = load_config(
        config_file
    )
    pretrain_ckpt_path = ckpt_path
    # merge the pretrain and finetune config
    pretrain_config.update(finetune_config)

    pretrain_config['warmup']['criterion']['sce']['num_classes'] = args.num_classes
    pretrain_config['warmup']['num_epochs'] = args.epoch_warmup

    args.batch_size = 128
    logging.info("\n===Prepare data===")
    
    
    
    train_transform = get_transform_prefetch(args.dataset, *([args.input_height,args.input_width]) , train = True,prefetch=args.prefetch)
    x = result['bd_train']['x']
    y = result['bd_train']['y'] # note: 这里x, y的意义不清楚，bd_train不清楚是哪里来的——————————————————————————————————————————————————————————————————？
    dataset_ori = xy_iter( # note: 迭代x, y, train_transform
        x,y,train_transform
    ) # note: cifar10和一些输入信息已经准备好了(dataset_ori已经准备好), 下面开始投毒
    
    
    
    dataset = PoisonLabelDataset(dataset_ori, train_transform, np.zeros(len(dataset_ori)), True,args) 
    # note: 用np.zeros()返回来一个给定形状和类型的用0填充的数组, 用0是为了从一个未被污染的状态开始
    poison_train_loader_ori = torch.utils.data.DataLoader(dataset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)
    poison_eval_loader_ori = torch.utils.data.DataLoader(dataset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=False,pin_memory=True)
    if args.prefetch:
        poison_train_loader = PrefetchLoader(poison_train_loader_ori, dataset.mean, dataset.std) 
        poison_eval_loader = PrefetchLoader(poison_eval_loader_ori, dataset.mean, dataset.std)
    else:
        poison_train_loader = poison_train_loader_ori 
        poison_eval_loader = poison_eval_loader_ori  
    # note: cifar10_poisoned_train和cifar10_poisoned_eval准备好了, 还差个test, 所以下面是测试集的生成
    
    
    
    test_transform = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = result['bd_test']['x']
    y = result['bd_test']['y']
    dataset_ori_bd = xy_iter(
        x,y,train_transform
    ) # note: 被污染后的cifar10和一些输入信息已经准备好了(dataset_ori_bd已经准备好)
    
    
    
    dataset_te_bd = PoisonLabelDataset(dataset_ori_bd, test_transform, np.zeros(len(dataset_ori_bd)), False,args)
    poison_test_loader = torch.utils.data.DataLoader(dataset_te_bd, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=False,pin_memory=True)
    # note: cifar10_poisoned_test is ready!
    x = result['clean_test']['x']
    y = result['clean_test']['y']
    dataset_ori_cl = xy_iter(
        x,y,train_transform
    )
    
    
    
    dataset_te_cl = PoisonLabelDataset(dataset_ori_cl, test_transform, np.zeros(len(dataset_ori_cl)), False,args) # note: 不知道为什么要用PoisonLabelDataset产生干净的？
    clean_test_loader = torch.utils.data.DataLoader(dataset_te_cl, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=False,pin_memory=True)

    backbone = get_network_dbd(args)
    # backbone = self_model.backbone
    self_model = SelfModel(backbone)
    self_model = self_model.to(args.device)
    # # Load backbone from the pretrained model.
    loc = os.path.join(os.getcwd() + args.checkpoint_save, "self_latest_model.pt")
    load_state(
        self_model, pretrain_config["pretrain_checkpoint"], loc, args.device, logger
    )
    linear_model = LinearModel(backbone, backbone.feature_dim, args.num_classes) # note: 
    linear_model.linear.to(args.device)
    warmup_criterion = get_criterion(pretrain_config["warmup"]["criterion"])
    logger.info("Create criterion: {} for warmup".format(warmup_criterion))
    warmup_criterion = warmup_criterion.to(args.device)
    semi_criterion = get_criterion(pretrain_config["semi"]["criterion"])
    semi_criterion = semi_criterion.to(args.device)
    logger.info("Create criterion: {} for semi-training".format(semi_criterion))
    optimizer = get_optimizer(linear_model, pretrain_config["optimizer"])
    logger.info("Create optimizer: {}".format(optimizer))
    scheduler = get_scheduler(optimizer, pretrain_config["lr_scheduler"])
    logger.info("Create learning rete scheduler: {}".format(pretrain_config["lr_scheduler"]))
    if args.checkpoint_load == '' or args.checkpoint_load is None:
        resume = 'False'
    resumed_epoch, best_acc, best_epoch = load_state(
        linear_model,
        resume,
        args.checkpoint_load,
        gpu,
        logger,
        optimizer,
        scheduler,
        is_best=True,
    )

    # b. learning model using extracted features
    num_epochs = args.epoch_warmup + args.epochs
    for epoch in range(num_epochs - resumed_epoch):
        logger.info("===Epoch: {}/{}===".format(epoch + resumed_epoch + 1, num_epochs))
        if (epoch + resumed_epoch + 1) <= args.epoch_warmup:
            logger.info("Poisoned linear warmup...")
            poison_train_result = poison_linear_train(
                linear_model, poison_train_loader, warmup_criterion, optimizer, logger,
            ) # note: 这个函数用于训练模型的全连接层，同时可以选择性地冻结模型的backbone部分，属于监督学习
        else:
            record_list = poison_linear_record(
                linear_model, poison_eval_loader, warmup_criterion
            )
            logger.info("Mining clean data from poisoned dataset...")
            # c. the samples with poor confidence were excluded, and semi-supervised learning was used to continue the learning model
            semi_idx = get_semi_idx(record_list, args.epsilon, logger)
            xdata = MixMatchDataset(dataset, semi_idx, labeled=True,args=args)
            udata = MixMatchDataset(dataset, semi_idx, labeled=False,args=args)
            pretrain_config["semi"]["loader"]['num_workers'] = args.num_workers_semi
            xloader = get_loader(
                xdata, pretrain_config["semi"]["loader"], shuffle=True, drop_last=True
            )
            uloader = get_loader(
                udata, pretrain_config["semi"]["loader"], shuffle=True, drop_last=True
            )
            logger.info("MixMatch training...")
            poison_train_result = mixmatch_train( # note: MixMatch 是一种结合了混合样本（Mixup）和一致性正则化（Consistency Regularization）的方法，它同时对有标签和无标签的数据进行训练，以提高模型的泛化能力。
                args,
                linear_model,
                xloader,
                uloader,
                semi_criterion,
                optimizer,
                epoch,
                logger,
                **pretrain_config["semi"]["mixmatch"]
            )
        logger.info("Test model on clean data...")
        clean_test_result = linear_test( # note: 测试性能
            linear_model, clean_test_loader, warmup_criterion, logger
        )
        logger.info("Test model on poison data...")
        poison_test_result = linear_test( # note: 测试性能
            linear_model, poison_test_loader, warmup_criterion, logger
        )
        if scheduler is not None:
            scheduler.step()
            logger.info(
                "Adjust learning rate to {}".format(optimizer.param_groups[0]["lr"])
            )
        result = {
            "poison_train": poison_train_result,
            "poison_test": poison_test_result,
            "clean_test": clean_test_result,
        }
        result2csv(result, os.getcwd() + args.log)

        is_best = False
        if clean_test_result["acc"] > best_acc: # note: 如果不达标, 就一直弄
            is_best = True
            best_acc = clean_test_result["acc"]
            best_epoch = epoch + resumed_epoch + 1
        logger.info("Best test accuaracy {} in epoch {}".format(best_acc, best_epoch))

        saved_dict = {
            "epoch": epoch + resumed_epoch + 1,
            "result": result,
            "model_state_dict": linear_model.state_dict(),
            "optimizer_state_dict": optimizer.state_dict(),
            "best_acc": best_acc,
            "best_epoch": best_epoch,
        }
        if scheduler is not None:
            saved_dict["scheduler_state_dict"] = scheduler.state_dict()

        if is_best:
            ckpt_path = os.path.join(os.getcwd() + args.checkpoint_save, "best_model.pt")
            torch.save(saved_dict, ckpt_path)
            logger.info("Save the best model to {}".format(ckpt_path))
        ckpt_path = os.path.join(os.getcwd() + args.checkpoint_save, "semi_latest_model.pt")
        torch.save(saved_dict, ckpt_path)
        logger.info("Save the latest model to {}".format(ckpt_path))

    result = {}
    result['model'] = linear_model
    return result

if __name__ == '__main__':
    
   ### 1. basic setting: args
    args = get_args()
    with open(args.yaml_path, 'r') as stream: 
        config = yaml.safe_load(stream) 
    config.update({k:v for k,v in args.__dict__.items() if v is not None})
    args.__dict__ = config
    args.num_classes = get_num_classes(args.dataset)
    args.input_height, args.input_width, args.input_channel = get_input_shape(args.dataset)
    args.img_size = (args.input_height, args.input_width, args.input_channel)
    
    save_path = '/record/' + args.result_file
    if args.checkpoint_save is None:
        args.checkpoint_save = save_path + '/record/defence/dbd/'
        if not (os.path.exists(os.getcwd() + args.checkpoint_save)):
            os.makedirs(os.getcwd() + args.checkpoint_save) 
    if args.log is None:
        args.log = save_path + '/saved/dbd/'
        if not (os.path.exists(os.getcwd() + args.log)):
            os.makedirs(os.getcwd() + args.log) 
    args.save_path = save_path
    
    ### 2. attack result(model, train data, test data)
    result = load_attack_result(os.getcwd() + save_path + '/attack_result.pt') 
    
    ### 3. dbd defense:
    print("Continue training...")
    result_defense = dbd(args,result)

    ### 4. test the result and get ASR, ACC, RC
    result_defense['model'].eval()
    result_defense['model'].to(args.device) 
    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = result['bd_test']['x']
    y = result['bd_test']['y']
    data_bd_test = list(zip(x,y))
    data_bd_testset = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_bd_test,
        poison_idx=np.zeros(len(data_bd_test)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    data_bd_loader = torch.utils.data.DataLoader(data_bd_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)

    asr_acc = 0 # note: 计算attack success rate(ASR)————prediction accuracy of poisoned samples to the target class
    for i, (inputs,labels) in enumerate(data_bd_loader):  # type: ignore
        inputs, labels = inputs.to(args.device), labels.to(args.device)
        outputs = result_defense['model'](inputs)
        pre_label = torch.max(outputs,dim=1)[1]
        asr_acc += torch.sum(pre_label == labels)
    asr_acc = asr_acc/len(data_bd_test)

    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = result['clean_test']['x']
    y = result['clean_test']['y']
    data_clean_test = list(zip(x,y))
    data_clean_testset = prepro_cls_DatasetBD(
        full_dataset_without_transform=data_clean_test,
        poison_idx=np.zeros(len(data_clean_test)),  # one-hot to determine which image may take bd_transform
        bd_image_pre_transform=None,
        bd_label_pre_transform=None,
        ori_image_transform_in_loading=tran,
        ori_label_transform_in_loading=None,
        add_details_in_preprocess=False,
    )
    data_clean_loader = torch.utils.data.DataLoader(data_clean_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)

    clean_acc = 0 # note: 计算clean accuracy (C-Acc)————prediction accuracy of clean samples
    for i, (inputs,labels) in enumerate(data_clean_loader):  # type: ignore
        inputs, labels = inputs.to(args.device), labels.to(args.device)
        outputs = result_defense['model'](inputs)
        pre_label = torch.max(outputs,dim=1)[1]
        clean_acc += torch.sum(pre_label == labels)
    clean_acc = clean_acc/len(data_clean_test)

    tran = get_transform(args.dataset, *([args.input_height,args.input_width]) , train = False)
    x = result['bd_test']['x']
    robust_acc = -1
    if 'original_targets' in result['bd_test']:
        y_ori = result['bd_test']['original_targets']
        if y_ori is not None:
            if len(y_ori) != len(x):
                y_idx = result['bd_test']['original_index']
                y = y_ori[y_idx]
            else :
                y = y_ori
            data_bd_test = list(zip(x,y))
            data_bd_testset = prepro_cls_DatasetBD(
                full_dataset_without_transform=data_bd_test,
                poison_idx=np.zeros(len(data_bd_test)),  # one-hot to determine which image may take bd_transform
                bd_image_pre_transform=None,
                bd_label_pre_transform=None,
                ori_image_transform_in_loading=tran,
                ori_label_transform_in_loading=None,
                add_details_in_preprocess=False,
            )
            data_bd_loader = torch.utils.data.DataLoader(data_bd_testset, batch_size=args.batch_size, num_workers=args.num_workers,drop_last=False, shuffle=True,pin_memory=True)
        
            robust_acc = 0 # note: robust accuracy(R-Acc)————prediction accuracy of poisoned samples to the original class
            for i, (inputs,labels) in enumerate(data_bd_loader):  # type: ignore
                inputs, labels = inputs.to(args.device), labels.to(args.device)
                outputs = result_defense['model'](inputs)
                pre_label = torch.max(outputs,dim=1)[1]
                robust_acc += torch.sum(pre_label == labels)
            robust_acc = robust_acc/len(data_bd_test)


    if not (os.path.exists(os.getcwd() + f'{save_path}/dbd/')):
        os.makedirs(os.getcwd() + f'{save_path}/dbd/')
    torch.save(
    {
        'model_name':args.model,
        'model': result_defense['model'].cpu().state_dict(),
        'asr': asr_acc,
        'acc': clean_acc,
        'ra': robust_acc
    },
    f'./{save_path}/dbd/defense_result.pt'
    )
    # note: 输入positioned_sample，得到提纯后的feature extractor，但是不确定是否输出全连接层，此外，没看到输出干净样本





#                     GNU GENERAL PUBLIC LICENSE
#                        Version 3, 29 June 2007

#  Copyright (C) 2007 Free Software Foundation, Inc. <https://fsf.org/>
#  Everyone is permitted to copy and distribute verbatim copies
#  of this license document, but changing it is not allowed.

#                             Preamble

#   The GNU General Public License is a free, copyleft license for
# software and other kinds of works.

#   The licenses for most software and other practical works are designed
# to take away your freedom to share and change the works.  By contrast,
# the GNU General Public License is intended to guarantee your freedom to
# share and change all versions of a program--to make sure it remains free
# software for all its users.  We, the Free Software Foundation, use the
# GNU General Public License for most of our software; it applies also to
# any other work released this way by its authors.  You can apply it to
# your programs, too.

#   When we speak of free software, we are referring to freedom, not
# price.  Our General Public Licenses are designed to make sure that you
# have the freedom to distribute copies of free software (and charge for
# them if you wish), that you receive source code or can get it if you
# want it, that you can change the software or use pieces of it in new
# free programs, and that you know you can do these things.

#   To protect your rights, we need to prevent others from denying you
# these rights or asking you to surrender the rights.  Therefore, you have
# certain responsibilities if you distribute copies of the software, or if
# you modify it: responsibilities to respect the freedom of others.

#   For example, if you distribute copies of such a program, whether
# gratis or for a fee, you must pass on to the recipients the same
# freedoms that you received.  You must make sure that they, too, receive
# or can get the source code.  And you must show them these terms so they
# know their rights.

#   Developers that use the GNU GPL protect your rights with two steps:
# (1) assert copyright on the software, and (2) offer you this License
# giving you legal permission to copy, distribute and/or modify it.

#   For the developers' and authors' protection, the GPL clearly explains
# that there is no warranty for this free software.  For both users' and
# authors' sake, the GPL requires that modified versions be marked as
# changed, so that their problems will not be attributed erroneously to
# authors of previous versions.

#   Some devices are designed to deny users access to install or run
# modified versions of the software inside them, although the manufacturer
# can do so.  This is fundamentally incompatible with the aim of
# protecting users' freedom to change the software.  The systematic
# pattern of such abuse occurs in the area of products for individuals to
# use, which is precisely where it is most unacceptable.  Therefore, we
# have designed this version of the GPL to prohibit the practice for those
# products.  If such problems arise substantially in other domains, we
# stand ready to extend this provision to those domains in future versions
# of the GPL, as needed to protect the freedom of users.

#   Finally, every program is threatened constantly by software patents.
# States should not allow patents to restrict development and use of
# software on general-purpose computers, but in those that do, we wish to
# avoid the special danger that patents applied to a free program could
# make it effectively proprietary.  To prevent this, the GPL assures that
# patents cannot be used to render the program non-free.

#   The precise terms and conditions for copying, distribution and
# modification follow.

#                        TERMS AND CONDITIONS

#   0. Definitions.

#   "This License" refers to version 3 of the GNU General Public License.

#   "Copyright" also means copyright-like laws that apply to other kinds of
# works, such as semiconductor masks.

#   "The Program" refers to any copyrightable work licensed under this
# License.  Each licensee is addressed as "you".  "Licensees" and
# "recipients" may be individuals or organizations.

#   To "modify" a work means to copy from or adapt all or part of the work
# in a fashion requiring copyright permission, other than the making of an
# exact copy.  The resulting work is called a "modified version" of the
# earlier work or a work "based on" the earlier work.

#   A "covered work" means either the unmodified Program or a work based
# on the Program.

#   To "propagate" a work means to do anything with it that, without
# permission, would make you directly or secondarily liable for
# infringement under applicable copyright law, except executing it on a
# computer or modifying a private copy.  Propagation includes copying,
# distribution (with or without modification), making available to the
# public, and in some countries other activities as well.

#   To "convey" a work means any kind of propagation that enables other
# parties to make or receive copies.  Mere interaction with a user through
# a computer network, with no transfer of a copy, is not conveying.

#   An interactive user interface displays "Appropriate Legal Notices"
# to the extent that it includes a convenient and prominently visible
# feature that (1) displays an appropriate copyright notice, and (2)
# tells the user that there is no warranty for the work (except to the
# extent that warranties are provided), that licensees may convey the
# work under this License, and how to view a copy of this License.  If
# the interface presents a list of user commands or options, such as a
# menu, a prominent item in the list meets this criterion.

#   1. Source Code.

#   The "source code" for a work means the preferred form of the work
# for making modifications to it.  "Object code" means any non-source
# form of a work.

#   A "Standard Interface" means an interface that either is an official
# standard defined by a recognized standards body, or, in the case of
# interfaces specified for a particular programming language, one that
# is widely used among developers working in that language.

#   The "System Libraries" of an executable work include anything, other
# than the work as a whole, that (a) is included in the normal form of
# packaging a Major Component, but which is not part of that Major
# Component, and (b) serves only to enable use of the work with that
# Major Component, or to implement a Standard Interface for which an
# implementation is available to the public in source code form.  A
# "Major Component", in this context, means a major essential component
# (kernel, window system, and so on) of the specific operating system
# (if any) on which the executable work runs, or a compiler used to
# produce the work, or an object code interpreter used to run it.

#   The "Corresponding Source" for a work in object code form means all
# the source code needed to generate, install, and (for an executable
# work) run the object code and to modify the work, including scripts to
# control those activities.  However, it does not include the work's
# System Libraries, or general-purpose tools or generally available free
# programs which are used unmodified in performing those activities but
# which are not part of the work.  For example, Corresponding Source
# includes interface definition files associated with source files for
# the work, and the source code for shared libraries and dynamically
# linked subprograms that the work is specifically designed to require,
# such as by intimate data communication or control flow between those
# subprograms and other parts of the work.

#   The Corresponding Source need not include anything that users
# can regenerate automatically from other parts of the Corresponding
# Source.

#   The Corresponding Source for a work in source code form is that
# same work.

#   2. Basic Permissions.

#   All rights granted under this License are granted for the term of
# copyright on the Program, and are irrevocable provided the stated
# conditions are met.  This License explicitly affirms your unlimited
# permission to run the unmodified Program.  The output from running a
# covered work is covered by this License only if the output, given its
# content, constitutes a covered work.  This License acknowledges your
# rights of fair use or other equivalent, as provided by copyright law.

#   You may make, run and propagate covered works that you do not
# convey, without conditions so long as your license otherwise remains
# in force.  You may convey covered works to others for the sole purpose
# of having them make modifications exclusively for you, or provide you
# with facilities for running those works, provided that you comply with
# the terms of this License in conveying all material for which you do
# not control copyright.  Those thus making or running the covered works
# for you must do so exclusively on your behalf, under your direction
# and control, on terms that prohibit them from making any copies of
# your copyrighted material outside their relationship with you.

#   Conveying under any other circumstances is permitted solely under
# the conditions stated below.  Sublicensing is not allowed; section 10
# makes it unnecessary.

#   3. Protecting Users' Legal Rights From Anti-Circumvention Law.

#   No covered work shall be deemed part of an effective technological
# measure under any applicable law fulfilling obligations under article
# 11 of the WIPO copyright treaty adopted on 20 December 1996, or
# similar laws prohibiting or restricting circumvention of such
# measures.

#   When you convey a covered work, you waive any legal power to forbid
# circumvention of technological measures to the extent such circumvention
# is effected by exercising rights under this License with respect to
# the covered work, and you disclaim any intention to limit operation or
# modification of the work as a means of enforcing, against the work's
# users, your or third parties' legal rights to forbid circumvention of
# technological measures.

#   4. Conveying Verbatim Copies.

#   You may convey verbatim copies of the Program's source code as you
# receive it, in any medium, provided that you conspicuously and
# appropriately publish on each copy an appropriate copyright notice;
# keep intact all notices stating that this License and any
# non-permissive terms added in accord with section 7 apply to the code;
# keep intact all notices of the absence of any warranty; and give all
# recipients a copy of this License along with the Program.

#   You may charge any price or no price for each copy that you convey,
# and you may offer support or warranty protection for a fee.

#   5. Conveying Modified Source Versions.

#   You may convey a work based on the Program, or the modifications to
# produce it from the Program, in the form of source code under the
# terms of section 4, provided that you also meet all of these conditions:

#     a) The work must carry prominent notices stating that you modified
#     it, and giving a relevant date.

#     b) The work must carry prominent notices stating that it is
#     released under this License and any conditions added under section
#     7.  This requirement modifies the requirement in section 4 to
#     "keep intact all notices".

#     c) You must license the entire work, as a whole, under this
#     License to anyone who comes into possession of a copy.  This
#     License will therefore apply, along with any applicable section 7
#     additional terms, to the whole of the work, and all its parts,
#     regardless of how they are packaged.  This License gives no
#     permission to license the work in any other way, but it does not
#     invalidate such permission if you have separately received it.

#     d) If the work has interactive user interfaces, each must display
#     Appropriate Legal Notices; however, if the Program has interactive
#     interfaces that do not display Appropriate Legal Notices, your
#     work need not make them do so.

#   A compilation of a covered work with other separate and independent
# works, which are not by their nature extensions of the covered work,
# and which are not combined with it such as to form a larger program,
# in or on a volume of a storage or distribution medium, is called an
# "aggregate" if the compilation and its resulting copyright are not
# used to limit the access or legal rights of the compilation's users
# beyond what the individual works permit.  Inclusion of a covered work
# in an aggregate does not cause this License to apply to the other
# parts of the aggregate.

#   6. Conveying Non-Source Forms.

#   You may convey a covered work in object code form under the terms
# of sections 4 and 5, provided that you also convey the
# machine-readable Corresponding Source under the terms of this License,
# in one of these ways:

#     a) Convey the object code in, or embodied in, a physical product
#     (including a physical distribution medium), accompanied by the
#     Corresponding Source fixed on a durable physical medium
#     customarily used for software interchange.

#     b) Convey the object code in, or embodied in, a physical product
#     (including a physical distribution medium), accompanied by a
#     written offer, valid for at least three years and valid for as
#     long as you offer spare parts or customer support for that product
#     model, to give anyone who possesses the object code either (1) a
#     copy of the Corresponding Source for all the software in the
#     product that is covered by this License, on a durable physical
#     medium customarily used for software interchange, for a price no
#     more than your reasonable cost of physically performing this
#     conveying of source, or (2) access to copy the
#     Corresponding Source from a network server at no charge.

#     c) Convey individual copies of the object code with a copy of the
#     written offer to provide the Corresponding Source.  This
#     alternative is allowed only occasionally and noncommercially, and
#     only if you received the object code with such an offer, in accord
#     with subsection 6b.

#     d) Convey the object code by offering access from a designated
#     place (gratis or for a charge), and offer equivalent access to the
#     Corresponding Source in the same way through the same place at no
#     further charge.  You need not require recipients to copy the
#     Corresponding Source along with the object code.  If the place to
#     copy the object code is a network server, the Corresponding Source
#     may be on a different server (operated by you or a third party)
#     that supports equivalent copying facilities, provided you maintain
#     clear directions next to the object code saying where to find the
#     Corresponding Source.  Regardless of what server hosts the
#     Corresponding Source, you remain obligated to ensure that it is
#     available for as long as needed to satisfy these requirements.

#     e) Convey the object code using peer-to-peer transmission, provided
#     you inform other peers where the object code and Corresponding
#     Source of the work are being offered to the general public at no
#     charge under subsection 6d.

#   A separable portion of the object code, whose source code is excluded
# from the Corresponding Source as a System Library, need not be
# included in conveying the object code work.

#   A "User Product" is either (1) a "consumer product", which means any
# tangible personal property which is normally used for personal, family,
# or household purposes, or (2) anything designed or sold for incorporation
# into a dwelling.  In determining whether a product is a consumer product,
# doubtful cases shall be resolved in favor of coverage.  For a particular
# product received by a particular user, "normally used" refers to a
# typical or common use of that class of product, regardless of the status
# of the particular user or of the way in which the particular user
# actually uses, or expects or is expected to use, the product.  A product
# is a consumer product regardless of whether the product has substantial
# commercial, industrial or non-consumer uses, unless such uses represent
# the only significant mode of use of the product.

#   "Installation Information" for a User Product means any methods,
# procedures, authorization keys, or other information required to install
# and execute modified versions of a covered work in that User Product from
# a modified version of its Corresponding Source.  The information must
# suffice to ensure that the continued functioning of the modified object
# code is in no case prevented or interfered with solely because
# modification has been made.

#   If you convey an object code work under this section in, or with, or
# specifically for use in, a User Product, and the conveying occurs as
# part of a transaction in which the right of possession and use of the
# User Product is transferred to the recipient in perpetuity or for a
# fixed term (regardless of how the transaction is characterized), the
# Corresponding Source conveyed under this section must be accompanied
# by the Installation Information.  But this requirement does not apply
# if neither you nor any third party retains the ability to install
# modified object code on the User Product (for example, the work has
# been installed in ROM).

#   The requirement to provide Installation Information does not include a
# requirement to continue to provide support service, warranty, or updates
# for a work that has been modified or installed by the recipient, or for
# the User Product in which it has been modified or installed.  Access to a
# network may be denied when the modification itself materially and
# adversely affects the operation of the network or violates the rules and
# protocols for communication across the network.

#   Corresponding Source conveyed, and Installation Information provided,
# in accord with this section must be in a format that is publicly
# documented (and with an implementation available to the public in
# source code form), and must require no special password or key for
# unpacking, reading or copying.

#   7. Additional Terms.

#   "Additional permissions" are terms that supplement the terms of this
# License by making exceptions from one or more of its conditions.
# Additional permissions that are applicable to the entire Program shall
# be treated as though they were included in this License, to the extent
# that they are valid under applicable law.  If additional permissions
# apply only to part of the Program, that part may be used separately
# under those permissions, but the entire Program remains governed by
# this License without regard to the additional permissions.

#   When you convey a copy of a covered work, you may at your option
# remove any additional permissions from that copy, or from any part of
# it.  (Additional permissions may be written to require their own
# removal in certain cases when you modify the work.)  You may place
# additional permissions on material, added by you to a covered work,
# for which you have or can give appropriate copyright permission.

#   Notwithstanding any other provision of this License, for material you
# add to a covered work, you may (if authorized by the copyright holders of
# that material) supplement the terms of this License with terms:

#     a) Disclaiming warranty or limiting liability differently from the
#     terms of sections 15 and 16 of this License; or

#     b) Requiring preservation of specified reasonable legal notices or
#     author attributions in that material or in the Appropriate Legal
#     Notices displayed by works containing it; or

#     c) Prohibiting misrepresentation of the origin of that material, or
#     requiring that modified versions of such material be marked in
#     reasonable ways as different from the original version; or

#     d) Limiting the use for publicity purposes of names of licensors or
#     authors of the material; or

#     e) Declining to grant rights under trademark law for use of some
#     trade names, trademarks, or service marks; or

#     f) Requiring indemnification of licensors and authors of that
#     material by anyone who conveys the material (or modified versions of
#     it) with contractual assumptions of liability to the recipient, for
#     any liability that these contractual assumptions directly impose on
#     those licensors and authors.

#   All other non-permissive additional terms are considered "further
# restrictions" within the meaning of section 10.  If the Program as you
# received it, or any part of it, contains a notice stating that it is
# governed by this License along with a term that is a further
# restriction, you may remove that term.  If a license document contains
# a further restriction but permits relicensing or conveying under this
# License, you may add to a covered work material governed by the terms
# of that license document, provided that the further restriction does
# not survive such relicensing or conveying.

#   If you add terms to a covered work in accord with this section, you
# must place, in the relevant source files, a statement of the
# additional terms that apply to those files, or a notice indicating
# where to find the applicable terms.

#   Additional terms, permissive or non-permissive, may be stated in the
# form of a separately written license, or stated as exceptions;
# the above requirements apply either way.

#   8. Termination.

#   You may not propagate or modify a covered work except as expressly
# provided under this License.  Any attempt otherwise to propagate or
# modify it is void, and will automatically terminate your rights under
# this License (including any patent licenses granted under the third
# paragraph of section 11).

#   However, if you cease all violation of this License, then your
# license from a particular copyright holder is reinstated (a)
# provisionally, unless and until the copyright holder explicitly and
# finally terminates your license, and (b) permanently, if the copyright
# holder fails to notify you of the violation by some reasonable means
# prior to 60 days after the cessation.

#   Moreover, your license from a particular copyright holder is
# reinstated permanently if the copyright holder notifies you of the
# violation by some reasonable means, this is the first time you have
# received notice of violation of this License (for any work) from that
# copyright holder, and you cure the violation prior to 30 days after
# your receipt of the notice.

#   Termination of your rights under this section does not terminate the
# licenses of parties who have received copies or rights from you under
# this License.  If your rights have been terminated and not permanently
# reinstated, you do not qualify to receive new licenses for the same
# material under section 10.

#   9. Acceptance Not Required for Having Copies.

#   You are not required to accept this License in order to receive or
# run a copy of the Program.  Ancillary propagation of a covered work
# occurring solely as a consequence of using peer-to-peer transmission
# to receive a copy likewise does not require acceptance.  However,
# nothing other than this License grants you permission to propagate or
# modify any covered work.  These actions infringe copyright if you do
# not accept this License.  Therefore, by modifying or propagating a
# covered work, you indicate your acceptance of this License to do so.

#   10. Automatic Licensing of Downstream Recipients.

#   Each time you convey a covered work, the recipient automatically
# receives a license from the original licensors, to run, modify and
# propagate that work, subject to this License.  You are not responsible
# for enforcing compliance by third parties with this License.

#   An "entity transaction" is a transaction transferring control of an
# organization, or substantially all assets of one, or subdividing an
# organization, or merging organizations.  If propagation of a covered
# work results from an entity transaction, each party to that
# transaction who receives a copy of the work also receives whatever
# licenses to the work the party's predecessor in interest had or could
# give under the previous paragraph, plus a right to possession of the
# Corresponding Source of the work from the predecessor in interest, if
# the predecessor has it or can get it with reasonable efforts.

#   You may not impose any further restrictions on the exercise of the
# rights granted or affirmed under this License.  For example, you may
# not impose a license fee, royalty, or other charge for exercise of
# rights granted under this License, and you may not initiate litigation
# (including a cross-claim or counterclaim in a lawsuit) alleging that
# any patent claim is infringed by making, using, selling, offering for
# sale, or importing the Program or any portion of it.

#   11. Patents.

#   A "contributor" is a copyright holder who authorizes use under this
# License of the Program or a work on which the Program is based.  The
# work thus licensed is called the contributor's "contributor version".

#   A contributor's "essential patent claims" are all patent claims
# owned or controlled by the contributor, whether already acquired or
# hereafter acquired, that would be infringed by some manner, permitted
# by this License, of making, using, or selling its contributor version,
# but do not include claims that would be infringed only as a
# consequence of further modification of the contributor version.  For
# purposes of this definition, "control" includes the right to grant
# patent sublicenses in a manner consistent with the requirements of
# this License.

#   Each contributor grants you a non-exclusive, worldwide, royalty-free
# patent license under the contributor's essential patent claims, to
# make, use, sell, offer for sale, import and otherwise run, modify and
# propagate the contents of its contributor version.

#   In the following three paragraphs, a "patent license" is any express
# agreement or commitment, however denominated, not to enforce a patent
# (such as an express permission to practice a patent or covenant not to
# sue for patent infringement).  To "grant" such a patent license to a
# party means to make such an agreement or commitment not to enforce a
# patent against the party.

#   If you convey a covered work, knowingly relying on a patent license,
# and the Corresponding Source of the work is not available for anyone
# to copy, free of charge and under the terms of this License, through a
# publicly available network server or other readily accessible means,
# then you must either (1) cause the Corresponding Source to be so
# available, or (2) arrange to deprive yourself of the benefit of the
# patent license for this particular work, or (3) arrange, in a manner
# consistent with the requirements of this License, to extend the patent
# license to downstream recipients.  "Knowingly relying" means you have
# actual knowledge that, but for the patent license, your conveying the
# covered work in a country, or your recipient's use of the covered work
# in a country, would infringe one or more identifiable patents in that
# country that you have reason to believe are valid.

#   If, pursuant to or in connection with a single transaction or
# arrangement, you convey, or propagate by procuring conveyance of, a
# covered work, and grant a patent license to some of the parties
# receiving the covered work authorizing them to use, propagate, modify
# or convey a specific copy of the covered work, then the patent license
# you grant is automatically extended to all recipients of the covered
# work and works based on it.

#   A patent license is "discriminatory" if it does not include within
# the scope of its coverage, prohibits the exercise of, or is
# conditioned on the non-exercise of one or more of the rights that are
# specifically granted under this License.  You may not convey a covered
# work if you are a party to an arrangement with a third party that is
# in the business of distributing software, under which you make payment
# to the third party based on the extent of your activity of conveying
# the work, and under which the third party grants, to any of the
# parties who would receive the covered work from you, a discriminatory
# patent license (a) in connection with copies of the covered work
# conveyed by you (or copies made from those copies), or (b) primarily
# for and in connection with specific products or compilations that
# contain the covered work, unless you entered into that arrangement,
# or that patent license was granted, prior to 28 March 2007.

#   Nothing in this License shall be construed as excluding or limiting
# any implied license or other defenses to infringement that may
# otherwise be available to you under applicable patent law.

#   12. No Surrender of Others' Freedom.

#   If conditions are imposed on you (whether by court order, agreement or
# otherwise) that contradict the conditions of this License, they do not
# excuse you from the conditions of this License.  If you cannot convey a
# covered work so as to satisfy simultaneously your obligations under this
# License and any other pertinent obligations, then as a consequence you may
# not convey it at all.  For example, if you agree to terms that obligate you
# to collect a royalty for further conveying from those to whom you convey
# the Program, the only way you could satisfy both those terms and this
# License would be to refrain entirely from conveying the Program.

#   13. Use with the GNU Affero General Public License.

#   Notwithstanding any other provision of this License, you have
# permission to link or combine any covered work with a work licensed
# under version 3 of the GNU Affero General Public License into a single
# combined work, and to convey the resulting work.  The terms of this
# License will continue to apply to the part which is the covered work,
# but the special requirements of the GNU Affero General Public License,
# section 13, concerning interaction through a network will apply to the
# combination as such.

#   14. Revised Versions of this License.

#   The Free Software Foundation may publish revised and/or new versions of
# the GNU General Public License from time to time.  Such new versions will
# be similar in spirit to the present version, but may differ in detail to
# address new problems or concerns.

#   Each version is given a distinguishing version number.  If the
# Program specifies that a certain numbered version of the GNU General
# Public License "or any later version" applies to it, you have the
# option of following the terms and conditions either of that numbered
# version or of any later version published by the Free Software
# Foundation.  If the Program does not specify a version number of the
# GNU General Public License, you may choose any version ever published
# by the Free Software Foundation.

#   If the Program specifies that a proxy can decide which future
# versions of the GNU General Public License can be used, that proxy's
# public statement of acceptance of a version permanently authorizes you
# to choose that version for the Program.

#   Later license versions may give you additional or different
# permissions.  However, no additional obligations are imposed on any
# author or copyright holder as a result of your choosing to follow a
# later version.

#   15. Disclaimer of Warranty.

#   THERE IS NO WARRANTY FOR THE PROGRAM, TO THE EXTENT PERMITTED BY
# APPLICABLE LAW.  EXCEPT WHEN OTHERWISE STATED IN WRITING THE COPYRIGHT
# HOLDERS AND/OR OTHER PARTIES PROVIDE THE PROGRAM "AS IS" WITHOUT WARRANTY
# OF ANY KIND, EITHER EXPRESSED OR IMPLIED, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE.  THE ENTIRE RISK AS TO THE QUALITY AND PERFORMANCE OF THE PROGRAM
# IS WITH YOU.  SHOULD THE PROGRAM PROVE DEFECTIVE, YOU ASSUME THE COST OF
# ALL NECESSARY SERVICING, REPAIR OR CORRECTION.

#   16. Limitation of Liability.

#   IN NO EVENT UNLESS REQUIRED BY APPLICABLE LAW OR AGREED TO IN WRITING
# WILL ANY COPYRIGHT HOLDER, OR ANY OTHER PARTY WHO MODIFIES AND/OR CONVEYS
# THE PROGRAM AS PERMITTED ABOVE, BE LIABLE TO YOU FOR DAMAGES, INCLUDING ANY
# GENERAL, SPECIAL, INCIDENTAL OR CONSEQUENTIAL DAMAGES ARISING OUT OF THE
# USE OR INABILITY TO USE THE PROGRAM (INCLUDING BUT NOT LIMITED TO LOSS OF
# DATA OR DATA BEING RENDERED INACCURATE OR LOSSES SUSTAINED BY YOU OR THIRD
# PARTIES OR A FAILURE OF THE PROGRAM TO OPERATE WITH ANY OTHER PROGRAMS),
# EVEN IF SUCH HOLDER OR OTHER PARTY HAS BEEN ADVISED OF THE POSSIBILITY OF
# SUCH DAMAGES.

#   17. Interpretation of Sections 15 and 16.

#   If the disclaimer of warranty and limitation of liability provided
# above cannot be given local legal effect according to their terms,
# reviewing courts shall apply local law that most closely approximates
# an absolute waiver of all civil liability in connection with the
# Program, unless a warranty or assumption of liability accompanies a
# copy of the Program in return for a fee.

#                      END OF TERMS AND CONDITIONS

#             How to Apply These Terms to Your New Programs

#   If you develop a new program, and you want it to be of the greatest
# possible use to the public, the best way to achieve this is to make it
# free software which everyone can redistribute and change under these terms.

#   To do so, attach the following notices to the program.  It is safest
# to attach them to the start of each source file to most effectively
# state the exclusion of warranty; and each file should have at least
# the "copyright" line and a pointer to where the full notice is found.

#     <one line to give the program's name and a brief idea of what it does.>
#     Copyright (C) <year>  <name of author>

#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

# Also add information on how to contact you by electronic and paper mail.

#   If the program does terminal interaction, make it output a short
# notice like this when it starts in an interactive mode:

#     <program>  Copyright (C) <year>  <name of author>
#     This program comes with ABSOLUTELY NO WARRANTY; for details type `show w'.
#     This is free software, and you are welcome to redistribute it
#     under certain conditions; type `show c' for details.

# The hypothetical commands `show w' and `show c' should show the appropriate
# parts of the General Public License.  Of course, your program's commands
# might be different; for a GUI interface, you would use an "about box".

#   You should also get your employer (if you work as a programmer) or school,
# if any, to sign a "copyright disclaimer" for the program, if necessary.
# For more information on this, and how to apply and follow the GNU GPL, see
# <https://www.gnu.org/licenses/>.

#   The GNU General Public License does not permit incorporating your program
# into proprietary programs.  If your program is a subroutine library, you
# may consider it more useful to permit linking proprietary applications with
# the library.  If this is what you want to do, use the GNU Lesser General
# Public License instead of this License.  But first, please read
# <https://www.gnu.org/licenses/why-not-lgpl.html>.
