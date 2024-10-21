from django.shortcuts import render, redirect  
from django.http import HttpResponse, HttpResponseRedirect    
import subprocess  
from django.conf import settings  
import os  
from django.http import FileResponse  
from django.conf import settings  
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
# Create your views here.


# 通过在 http://127.0.0.1:8000/admin/ 中添加用户
# 启动Django的代码:
# python manage.py runserver
'''
# 在打开Django html的时候，一定要确保Django项目正在运行(记得用python manage.py runserver启动Django)，
# 再输入：http://127.0.0.1:8000/login/ 来查看具体页面，login这块儿可以换掉。不要直接在本地打开.html，否则Django不会去渲染Django的模板语言
'''
def test(request):
    return render(request, 'test.html')

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




# 主页面函数
def index(request):
    return render(request, 'test.html')


# 文件上传函数
def upload_file(request):
    message = None  # 初始化消息为空
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = request.FILES['file']
            if uploaded_file.name.endswith('.pt'):
                # 保存上传的文件到服务器固定路径
                file_path = os.path.join('record', uploaded_file.name)
                # 确保 record 文件夹存在，如果不存在则创建它
                os.makedirs('record', exist_ok=True)
                with open(file_path, 'wb+') as destination:
                    for chunk in uploaded_file.chunks():
                        destination.write(chunk)
                message = '文件上传成功'
            else:
                message = '文件格式不正确，请上传 .pt 格式的文件'
    else:
        form = UploadFileForm()
    return render(request, 'test.html', {'form': form, 'message': message})


# 按钮函数
# Ajax提供了异步更新的机制，可以在不重新加载整个页面的情况下，与服务器交换数据并更新网页的某部分，实现页面的局部更新。这种技术可以提高网页的响应速度和用户体验。
def ajax_path_dealer(request):
    if request.method == 'POST' and request.is_ajax():
        defense_type = request.POST.get('defense_type')

        # 可以根据需要对接收到的数据进行处理

        response_data = {
            'defense_type': defense_type
        }
        print(response_data['defense_type'])
        print("成功接收到数据,开始转变为路径....")
        if response_data['defense_type'] == "ac":
            current_directory = "D:/study/work/backdoorbench/BackdoorBench-1"
            # 构建绝对路径
            denfense_path = "D:/study/work/backdoorbench/BackdoorBench-1/defense/ac/ac.py"
            yaml_path = "D:/study/work/backdoorbench/BackdoorBench-1/config/defense/ac/cifar10.yaml"
            # D:\study\work\backdoorbench\BackdoorBench-1\djangoproject\djangoapp\upload_file
            # 创建命令列表
            command = [
                "python", denfense_path,
                "--yaml_path", yaml_path,
                "--epochs", "2"
            ]
            print("命令路径：" + " ".join(command))
            subprocess.run(command, check=True)
        if response_data['defense_type'] == "abl":
            print("开始转变为路径....")
        if response_data['defense_type'] == "anp":
            print("开始转变为路径....")
        if response_data['defense_type'] == "ft":
            print("开始转变为路径....")
        if response_data['defense_type'] == "fp":
            print("开始转变为路径....")
        if response_data['defense_type'] == "nad":
            print("开始转变为路径....")
        if response_data['defense_type'] == "nc":
            print("开始转变为路径....")
        if response_data['defense_type'] == "Spectral":
            print("开始转变为路径....")
        if response_data['defense_type'] == "DBD":
            print("开始转变为路径....")
            
        
        
        
        
        
        
        
        
        
        
        
        
        print("Job Done!")
        return JsonResponse(response_data)
        '''
        传统的页面请求（例如通过点击链接或提交表单）会导致整个页面重新加载或者跳转到新的页面，因为浏览器会根据服务器返回的响应直接刷新页面。
        而在Ajax请求中，浏览器通过 JavaScript 向服务器发送请求，但不会刷新整个页面。
        相反，它会在后台接收服务器返回的响应，并根据你在 JavaScript 中定义的处理函数来执行相应的操作。这使得页面可以在不刷新的情况下进行部分更新或执行其他操作，而不会中断用户的当前操作。
        所以return render(request, 'index.html', response_data)是不会跳转到index.htm l的，因为它只会在当前页面进行局部更新。
        '''
    else:
        return JsonResponse({'error': 'Invalid request'})






























