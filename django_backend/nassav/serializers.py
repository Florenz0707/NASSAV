from rest_framework import serializers
from .models import AVInfo


class AVInfoSerializer(serializers.ModelSerializer):
    """AVInfo序列化器"""
    class Meta:
        model = AVInfo
        fields = ['id', 'avid', 'title', 'source', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class AVInfoListSerializer(serializers.ModelSerializer):
    """AVInfo列表序列化器（仅返回avid和title）"""
    class Meta:
        model = AVInfo
        fields = ['avid', 'title']


class NewResourceSerializer(serializers.Serializer):
    """新增资源请求序列化器"""
    avid = serializers.CharField(max_length=50)


class DownloadRequestSerializer(serializers.Serializer):
    """下载请求序列化器"""
    avid = serializers.CharField(max_length=50)
