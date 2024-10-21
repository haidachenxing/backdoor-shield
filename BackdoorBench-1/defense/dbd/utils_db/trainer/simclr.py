import time

import torch
from torch.cuda.amp import autocast
from torch.cuda.amp import GradScaler
from torch.nn.parallel import DistributedDataParallel

from .log import AverageMeter, Record, tabulate_step_meter, tabulate_epoch_meter
from .utils import GatherLayer




# note: SimCLR是一种用于无监督视觉表示学习的对比学习方法。这是一个典型的深度学习训练循环，包括了数据加载、前向传播、损失计算、反向传播和参数更新等步骤。
def simclr_train(model, loader, criterion, optimizer, logger, amp=False): 
    loss_meter = AverageMeter("loss")
    meter_list = [loss_meter]

    model.train()
    gpu = next(model.parameters()).device
    ddp = isinstance(model, DistributedDataParallel)
    if amp:
        scaler = GradScaler()
    else:
        scaler = None
    start_time = time.time()
    for batch_idx, batch in enumerate(loader):
        img1, img2 = batch["img1"], batch["img2"]
        data = torch.cat([img1.unsqueeze(1), img2.unsqueeze(1)], dim=1)
        b, c, h, w = img1.size()
        data = data.view(-1, c, h, w)
        data = data.cuda(gpu, non_blocking=True)

        optimizer.zero_grad()
        if amp:
            with autocast():
                output = model(data).view(b, 2, -1)
                if ddp:
                    output = torch.cat(GatherLayer.apply(output), dim=0)
                loss = criterion(output)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            output = model(data).view(b, 2, -1)
            if ddp:
                output = torch.cat(GatherLayer.apply(output), dim=0)
            loss = criterion(output)
            loss.backward()
            optimizer.step()

        loss_meter.update(loss.item())

        tabulate_step_meter(batch_idx, len(loader), 3, meter_list, logger)

    logger.info("Training summary:")
    tabulate_epoch_meter(time.time() - start_time, meter_list, logger)
    result = {m.name: m.total_avg for m in meter_list}

    del loss, data, output
    torch.cuda.empty_cache()
    return result


def linear_train(model, loader, criterion, optimizer, logger):
    loss_meter = AverageMeter("loss")
    acc_meter = AverageMeter("acc")
    meter_list = [loss_meter, acc_meter]

    # Freeze the backbone.
    for param in model.backbone.parameters():
        param.require_grad = False
    model.train()
    gpu = next(model.parameters()).device
    start_time = time.time()
    for batch_idx, batch in enumerate(loader):
        data = batch["img"].cuda(gpu, non_blocking=True)
        target = batch["target"].cuda(gpu, non_blocking=True)
        with torch.no_grad():
            feature = model.backbone(data)
        output = model.linear(feature)
        criterion.reduction = "mean"
        loss = criterion(output, target)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        loss_meter.update(loss.item())
        pred = output.argmax(dim=1, keepdim=True)
        truth = pred.view_as(target).eq(target)
        acc_meter.update((torch.sum(truth).float() / len(truth)).item())

        tabulate_step_meter(batch_idx, len(loader), 3, meter_list, logger)

    # Unfreeze the backbone.
    for param in model.backbone.parameters():
        param.require_grad = True
    logger.info("Linear training summary:")
    tabulate_epoch_meter(time.time() - start_time, meter_list, logger)
    result = {m.name: m.total_avg for m in meter_list}
    return result

# note: 尽管函数名为 linear_test，但它实际上可以用于测试任何类型的模型，只要该模型能够接收图像数据并输出预测即可。
# note: 这个函数 linear_test 是用来测试一个模型（尤其是它的线性部分）在给定数据集上的性能。
def linear_test(model, loader, criterion, logger):
    loss_meter = AverageMeter("loss")
    acc_meter = AverageMeter("acc")
    meter_list = [loss_meter, acc_meter]

    model.eval()
    gpu = next(model.parameters()).device
    start_time = time.time()
    for batch_idx, batch in enumerate(loader):
        data = batch["img"].cuda(gpu, non_blocking=True)
        target = batch["target"].cuda(gpu, non_blocking=True)
        with torch.no_grad():
            output = model(data)
        criterion.reduction = "mean"
        loss = criterion(output, target)

        loss_meter.update(loss.item())
        pred = output.argmax(dim=1, keepdim=True)
        truth = pred.view_as(target).eq(target)
        acc_meter.update((torch.sum(truth).float() / len(truth)).item())

        tabulate_step_meter(batch_idx, len(loader), 2, meter_list, logger)

    logger.info("Linear test summary:")
    tabulate_epoch_meter(time.time() - start_time, meter_list, logger)
    result = {m.name: m.total_avg for m in meter_list}

    return result

# note: 这个函数用于训练模型的全连接层，同时可以选择性地冻结模型的backbone部分（即不让backbone的参数在训练过程中更新）。
# note: 它接收一个模型、数据加载器、损失函数、优化器、日志记录器和一个布尔值来决定是否冻结backbone。
# note: 在训练过程中，它计算了总损失、毒化数据的损失、干净数据的损失、总准确率、毒化数据的准确率和干净数据的准确率。
# note: 通过检查batch["poison"]，函数能够区分毒化数据和干净数据，并分别计算它们的损失和准确率。
# note: 最后，它返回包含所有这些度量的结果的字典。

def poison_linear_train(model, loader, criterion, optimizer, logger, frozen=True):
    loss_meter = AverageMeter("loss")
    poison_loss_meter = AverageMeter("poison loss")
    clean_loss_meter = AverageMeter("clean loss")
    acc_meter = AverageMeter("acc")
    poison_acc_meter = AverageMeter("poison acc")
    clean_acc_meter = AverageMeter("clean acc")
    meter_list = [
        loss_meter,
        poison_loss_meter,
        clean_loss_meter,
        acc_meter,
        poison_acc_meter,
        clean_acc_meter,
    ]

    if frozen:
        # Freeze the backbone.
        for param in model.backbone.parameters():
            param.require_grad = False
    model.train()
    gpu = next(model.parameters()).device
    start_time = time.time()
    for batch_idx, batch in enumerate(loader):
        data = batch["img"].cuda(gpu, non_blocking=True)
        target = batch["target"].cuda(gpu, non_blocking=True)
        if frozen:
            with torch.no_grad():
                feature = model.backbone(data)
        else:
            feature = model.backbone(data)
        output = model.linear(feature)
        criterion.reduction = "none"
        raw_loss = criterion(output, target)
        criterion.reduction = "mean"
        loss = criterion(output, target)
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        loss_meter.update(loss.item())
        pred = output.argmax(dim=1, keepdim=True)
        truth = pred.view_as(target).eq(target)
        acc_meter.update((torch.sum(truth).float() / len(truth)).item())
        poison_idx = torch.nonzero(batch["poison"], as_tuple=True)
        clean_idx = torch.nonzero(batch["poison"] - 1, as_tuple=True)
        # Not every batch contains poison data.
        if len(poison_idx[0]) != 0:
            poison_loss_meter.update(torch.mean(raw_loss[poison_idx]).item())
            poison_acc_meter.update(
                (torch.sum(truth[poison_idx]).float() / len(truth[poison_idx])).item()
            )
        clean_loss_meter.update(torch.mean(raw_loss[clean_idx]).item())
        clean_acc_meter.update(
            (torch.sum(truth[clean_idx]).float() / len(truth[clean_idx])).item()
        )

        tabulate_step_meter(batch_idx, len(loader), 3, meter_list, logger)

    if frozen:
        # Unfreeze the backbone.
        for param in model.backbone.parameters():
            param.require_grad = True
    logger.info("Linear training summary:")
    tabulate_epoch_meter(time.time() - start_time, meter_list, logger)
    result = {m.name: m.total_avg for m in meter_list}

    return result





# note: poison_linear_record这个函数用于记录模型在全连接层上的行为，包括目标标签、毒化标签、原始标签、损失和特征。
# note: 它接收一个模型、数据加载器和损失函数。
# note: 在评估模式下，它遍历数据加载器中的每个批次，计算特征和损失，并更新相应的记录。
# note: 最后，它返回包含所有这些记录的列表。
def poison_linear_record(model, loader, criterion):
    num_data = len(loader.dataset)
    target_record = Record("target", num_data)
    poison_record = Record("poison", num_data)
    origin_record = Record("origin", num_data)
    loss_record = Record("loss", num_data)
    feature_record = Record("feature", (num_data, model.backbone.feature_dim))
    record_list = [
        target_record,
        poison_record,
        origin_record,
        loss_record,
        feature_record,
    ]

    model.eval()
    gpu = next(model.parameters()).device
    for _, batch in enumerate(loader):
        data = batch["img"].cuda(gpu, non_blocking=True)
        target = batch["target"].cuda(gpu, non_blocking=True)
        with torch.no_grad():
            feature = model.backbone(data)
            output = model.linear(feature)
        criterion.reduction = "none"
        raw_loss = criterion(output, target)

        target_record.update(batch["target"])
        poison_record.update(batch["poison"])
        origin_record.update(batch["origin"])
        loss_record.update(raw_loss.cpu())
        feature_record.update(feature.cpu())

    return record_list
