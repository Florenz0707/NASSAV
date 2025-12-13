from rest_framework import serializers


class NewResourceSerializer(serializers.Serializer):
    """新增资源请求序列化器"""
    avid = serializers.CharField(max_length=50)


class DownloadRequestSerializer(serializers.Serializer):
    """下载请求序列化器"""
    avid = serializers.CharField(max_length=50)
