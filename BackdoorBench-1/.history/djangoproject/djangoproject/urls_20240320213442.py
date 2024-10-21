"""djangoproject URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from djangoapp import views
# 一个路径（即一个特定的URL模式）通常只对应一个视图函数或类。但是，一个视图函数或类可以对应多个路径。
# 当{% url 'abc' %}被调用时，Django会在urlpatterns中查找第一个name为'abc'的路径，并返回该路径的URL。即根据第三个参数找第一个参数，再找第二个参数。
# 一般像redirect('abc')这样的函数，会根据第一个参数找第二个参数。
# 不管哪种方式，核心都是找到第二个参数。
urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', views.user_login, name='login'),
    path('reset-password/', views.reset_password, name='reset-password'),
    path('index/', views.index, name='index'),
    path('signup/', views.user_signup, name='signup'),
    path('upload/execute_defense/', views.execute_defense, name='execute_defense'),
    path('upload/record', views.upload_file, name='upload_file'),
    path('upload/', views.upload, name='upload'),
    path('analyse/', views.analyse, name='analyse'),
    path('analyse/execute_analyse/', views.execute_analyse, name='execute_analyse'),
    path('analyse/download/', views.download, name='download'),
]


