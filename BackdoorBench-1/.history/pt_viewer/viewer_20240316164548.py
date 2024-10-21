'''
import torch
import numpy as np

# 加载PyTorch张量
pt = torch.load('../record/cifar10_preactresnet18_badnet_0_1/attack_result.pt')
with open('../pt_viewer/badnet_attack_result.txt', 'w') as f:
    f.write(str(pt))
with open('../pt_viewer/badnet_attack_result.txt', 'r') as f:
    first_line = f.readline()
    print(first_line)
'''
import torch

# 加载PyTorch张量
pt = torch.load('../record/cifar10_preactresnet18_badnet_0_1/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_blended_0_1/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_Ft_Trojan_0_01/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_inputaware_0_1/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_lf_0_1/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_sig_0_1/attack_result.pt')
# pt = torch.load('../record/cifar10_preactresnet18_wanet_0_1/attack_result.pt')
# pt = torch.load('../record/lira_attack_attack_lira_PjWX/cifar10_preactresnet18_badnet_0_1/')

num_classes = pt['num_classes']
model_name = pt['model_name']
bd_train_x = pt['bd_train']['x']
bd_train_y = pt['bd_train']['y']
bd_train_original_index = pt['bd_train']['original_index']
bd_train_x_array_length = len(bd_train_x)
bd_train_y_array_length = len(bd_train_y)
bd_train_original_index_array_length = len(bd_train_original_index)

bd_test_x = pt['bd_test']['x']
bd_test_y = pt['bd_test']['y']
bd_test_original_index = pt['bd_test']['original_index']
bd_test_x_array_length = len(bd_test_x)
bd_test_y_array_length = len(bd_test_y)
bd_train_original_index_array_length = len(bd_train_original_index)
print("num_classes:", num_classes)
print("model_name:", model_name)
print("bd_train_y:", bd_train_y)
print("数组的元素个数为:", array_length)

