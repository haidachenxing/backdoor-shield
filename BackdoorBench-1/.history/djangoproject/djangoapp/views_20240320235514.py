from django.shortcuts import render, redirect  
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseRedirect    
import subprocess  
from django.conf import settings  
import os  
from django.http import FileResponse  
from djangoapp import models
import sqlite3
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm  
from django.http import JsonResponse  
from django.views.decorators.http import require_http_methods  
from django.views.decorators.csrf import csrf_exempt  
from .forms import UploadFileForm
import os
import subprocess
import zipfile

# Create your views here.


# 通过在 http://127.0.0.1:8000/admin/ 中添加用户
# 启动Django的代码:
# python manage.py runserver
'''
# 在打开Django html的时候，一定要确保Django项目正在运行(记得用python manage.py runserver启动Django)，
# 再输入：http://127.0.0.1:8000/login/ 来查看具体页面，login这块儿可以换掉。不要直接在本地打开.html，否则Django不会去渲染Django的模板语言
'''
def index(request):
    return render(request, 'index.html')

# 用户登录函数    
def user_login(request):

    if request.method == 'POST':
        print("进入页面")
        email = request.POST.get('email')  # 使用.get()方法可以避免KeyError  
        password = request.POST.get('password')  
        found_email = models.User.objects.filter(email=email).first()
        print("获取到信息")
        print(email)
        print(password)
        print(found_email)
        if found_email and found_email.password == password:  
            print('登录成功')  
            request.session['user_email'] = email # 在 Django 中，session 数据是存储在服务器端的，而不是存储在客户端（浏览器）上。
            return redirect(index)
        else:
            # 如果用户名或密码不正确，返回错误信息  
            return render(request, 'login.html', {'error': '用户名或密码不正确'}) 
    else: 
        return render(request,'login.html')

# 用户注册函数
def user_signup(request):
    
    if request.method == 'POST':
        print("进入页面")
        username = request.POST.get('username')  # 使用.get()方法可以避免KeyError  
        email = request.POST.get('email')
        password = request.POST.get('password')  
        found_email = models.User.objects.filter(email=email).first()
        if found_email:
            return render(request, 'signup.html', {'error': '电子邮件已经存在'})
        else:
            new_user = models.User(username=username, email=email, password=password)
            new_user.save()
            return redirect(user_login)
    else:
        return render(request, 'signup.html')


# 重置密码函数
def reset_password(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')  
        newpassword = request.POST.get('newpassword')
        found_email = models.User.objects.filter(email=email).first()
        if found_email:
            if found_email.password == password:
                print(found_email.password)
                found_email.password = newpassword
                found_email.save()
                print('修改成功')
                print(found_email.password)
                return redirect(user_login)
            else:
                return render(request, 'reset-password.html', {'error': '密码错误'})
        else:
            return render(request, 'reset-password.html', {'error': '电子邮件不存在，请点击下方signup进行注册'})
            
    else:
        return render(request, 'reset-password.html')

# 文件上传页面
def upload(request):
    return render(request, 'upload.html')
# 文件上传函数
def upload_file(request):
    message = None  # 初始化消息为空
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            if uploaded_file.name.endswith('.pt'):
                user_email = request.session.get('user_email') # 在 Django 中，session 数据是存储在服务器端的，而不是存储在客户端（浏览器）上。
                print("用户邮箱：" + user_email)

                # 获取文件名和文件大小
                file_name = uploaded_file.name
                file_size = uploaded_file.size

                # 创建以用户邮箱命名的文件夹
                user_folder = os.path.join('record', user_email)
                print("用户文件夹：" + user_folder)
                os.makedirs(user_folder, exist_ok=True)

                # 保存上传的文件到用户文件夹内
                file_path = os.path.join(user_folder, file_name)
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                
                # 将文件名和文件大小存储在会话中
                request.session['file_name'] = file_name
                request.session['file_size'] = file_size

                message = '文件上传成功'
            else:
                message = '文件格式不正确，请上传 .pt 格式的文件'
    else:
        form = UploadFileForm()
    return render(request, 'upload.html', {'form': form, 'message': message})
# 防御函数
def execute_defense(request):
    if request.method == 'POST':
        defense_algorithm = request.POST.get('defense_algorithm')
        print(defense_algorithm)
        print("成功接收到数据,开始转变为路径....")
        user_email = request.session.get('user_email') # 在 Django 中，session 数据是存储在服务器端的，而不是存储在客户端（浏览器）上。
        print("用户邮箱：" + user_email)
        current_directory = "D:/study/work/backdoorbench/BackdoorBench-1"
        if defense_algorithm == "ac":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/ac/ac.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/ac/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            # ++++++++++++++++++++++++++++++++++
            # visualize可视化
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/visualize.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", result_file_path,
                "--result_file_defense", result_file_path + "/ac"
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
            # ++++++++++++++++++++++++++++++++++
            # visualize_fre可视化
            # ++++++++++++++++++++++++++++++++++
            visualize_fre_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/visualize_fre.py"
            visualize_fre_command = [
                "python", visualize_fre_path,
                "--result_file_attack", result_file_path,
                "--result_file_defense", result_file_path + "/ac",
            ]
            print("visualize_pre命令路径：" + " ".join(visualize_fre_command))
            # subprocess.run(visualize_fre_command, check=True)
        if defense_algorithm == "abl":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/abl/abl.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/abl/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            # ++++++++++++++++++++++++++++++++++
            # visualize可视化
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/visualize.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", result_file_path,
                "--result_file_defense", result_file_path + "/abl"
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
            # ++++++++++++++++++++++++++++++++++
            # visualize_fre可视化
            # ++++++++++++++++++++++++++++++++++
            visualize_fre_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/visualize_fre.py"
            visualize_fre_command = [
                "python", visualize_fre_path,
                "--result_file_attack", result_file_path,
                "--result_file_defense", result_file_path + "/abl",
            ]
            print("visualize_pre命令路径：" + " ".join(visualize_fre_command))
            # subprocess.run(visualize_fre_command, check=True)
        if defense_algorithm == "anp":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/anp/anp.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/anp/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "ft":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/ft/ft.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/ft/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "fp":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/fp/fp.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/fp/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "nad":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/nad/nad.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/nad/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "nc":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/nc/nc.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/nc/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "spectral":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/spectral/spectral.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/spectral/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        if defense_algorithm == "dbd":
            # ++++++++++++++++++++++++++++++++++
            # 防御
            # ++++++++++++++++++++++++++++++++++
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/dbd/dbd.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/dbd/cifar10.yaml"
            result_file_path = user_email
            # 创建命令列表
            denfense_command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2",
                "--result_file", result_file_path
            ]
            print("denfense命令路径：" + " ".join(denfense_command))
            # subprocess.run(denfense_command, check=True)
            
        print("Job Done!")
        request.session['defense_algorithm'] = defense_algorithm
        request.session['user_email'] = user_email
        return redirect(analyse)
    else:
        return render(request, 'upload.html')



def analyse(request):
    defense_algorithm = request.session.get('defense_algorithm')
    file_name = request.session['file_name'] 
    file_size = request.session['file_size'] / 1024 / 1024
    user_email = request.session.get('user_email')
    print(file_name)
    print(file_size) # MB
    print(defense_algorithm)
    print(user_email)
    flag = request.session.get('flag', 0)
    message = None
    
    # 根据标志值设置消息
    if flag == 1:
        message = "已执行完成"
        # 清除标志值，以便下次分析时不会再显示消息
        request.session['flag'] = 0
    
    log_folder_path = 'D:/study/work/backdoorbench/BackdoorBench-1/djangoproject/record' + '/' + user_email + '/saved' + '/' + defense_algorithm

    # 获取文件夹中的所有日志文件，并按文件名排序
    log_files = sorted([file for file in os.listdir(log_folder_path) if file.endswith('.log')])

    if log_files:
        # 获取最新的日志文件路径
        latest_log_file_path = os.path.join(log_folder_path, log_files[-1])

        try:
            # 打开最新的日志文件并读取内容
            with open(latest_log_file_path, 'r') as file:
                log_file_content = file.read()
        except FileNotFoundError:
            # 如果文件不存在，返回空内容
            log_file_content = "Log file not found."
    else:
        # 如果没有日志文件，返回空内容
        log_file_content = None
    
    return render(request, 'analyse.html', {'defense_algorithm': defense_algorithm, 'file_name': file_name, 'file_size': file_size, 'log_file_content': log_file_content})

def execute_analyse(request):
    if request.method == 'POST':
        analyse_algorithm = request.POST.get('analyse_algorithm')
        print(analyse_algorithm)
        user_email = request.session.get('user_email')
        defense_algorithm = request.session.get('defense_algorithm')
        if analyse_algorithm == "1": # T-SNE
            # ++++++++++++++++++++++++++++++++++
            # T-SNE 
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/tsne.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", user_email,
                "--result_file_defense", user_email + "/" + defense_algorithm
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            subprocess.run(visualize_command, check=True)
        if analyse_algorithm == "2": # Neuron Activation
            # ++++++++++++++++++++++++++++++++++
            # Neuron Activation
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/na.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", user_email,
                "--result_file_defense", user_email + "/" + defense_algorithm
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
        if analyse_algorithm == "3": # Shapley Value
            # ++++++++++++++++++++++++++++++++++
            # Shapley Value
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/sv.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", user_email,
                "--result_file_defense", user_email + "/" + defense_algorithm
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
        if analyse_algorithm == "4": # Grad Cam
            # ++++++++++++++++++++++++++++++++++
            # Grad Cam
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/gc.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", user_email,
                "--result_file_defense", user_email + "/" + defense_algorithm
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
        if analyse_algorithm == "5": # Frequency
            # ++++++++++++++++++++++++++++++++++
            # Frequency
            # ++++++++++++++++++++++++++++++++++
            visualize_path = "D:/study/work/backdoorbench/BackdoorBench-1/visualization/visualize_fre.py"
            visualize_command = [
                "python", visualize_path,
                "--result_file_attack", user_email,
                "--result_file_defense", user_email + "/" + defense_algorithm
            ]
            print("visualize命令路径：" + " ".join(visualize_command))
            # subprocess.run(visualize_command, check=True)
        request.session['flag'] = 1
        return redirect(analyse)
    else:
        return render(request, 'analyse.html')


def download(request):
    # 设置要下载的文件夹路径
    user_email = request.session.get('user_email')
    folder_path = 'D:/study/work/backdoorbench/BackdoorBench-1/djangoproject/record' + '/' + user_email

    # 创建一个临时压缩文件
    zip_file_path = 'D:/study/work/backdoorbench/BackdoorBench-1/djangoproject/result.zip'
    with zipfile.ZipFile(zip_file_path, 'w') as zip_file:
        # 遍历文件夹中的文件并将其添加到压缩文件中
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, folder_path))

    # 使用 FileResponse 发送压缩文件到前端
    response = FileResponse(open(zip_file_path, 'rb'))
    response['Content-Disposition'] = 'attachment; filename="your_result.zip"'
    return response


def download_log(request):
    user_email = request.session.get('user_email')
    defense_algorithm = request.session.get('defense_algorithm')
    logs_folder_path = 'D:/study/work/backdoorbench/BackdoorBench-1/djangoproject/record' + '/' + user_email + '/saved' + '/' + defense_algorithm
    print(logs_folder_path)
    # D:\study\work\backdoorbench\BackdoorBench-1\djangoproject\record\hzzzzli@outlook.com\saved\ac
    zip_file_path = 'D:/study/work/backdoorbench/BackdoorBench-1/djangoproject/result_log.zip'
    with zipfile.ZipFile(zip_file_path, 'w') as zip_file:
        # 遍历文件夹中的文件并将其添加到压缩文件中
        for root, dirs, files in os.walk(logs_folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, logs_folder_path))

    # 使用 FileResponse 发送压缩文件到前端
    response = FileResponse(open(zip_file_path, 'rb'))
    response['Content-Disposition'] = 'attachment; filename="your_log.zip"'
    return response

    
    
    
    















