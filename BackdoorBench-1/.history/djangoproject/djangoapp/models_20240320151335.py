from django.db import models
from django.contrib.auth.models import User  
# Create your models here.

# 把模型迁移到数据库的代码：
# python manage.py makemigrations
# python manage.py migrate



# 用户表
# Create your models here.
# 用户表
class User(models.Model):
    username = models.CharField(max_length=128, unique=True)
    password = models.CharField(max_length=256)
    email = models.EmailField(unique=True)





    
    
    
    
    