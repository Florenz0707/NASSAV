from rest_framework import serializers


class NewResourceSerializer(serializers.Serializer):
    """新增资源请求序列化器"""
    avid = serializers.CharField(max_length=50)
    source = serializers.CharField(max_length=50, default='any', required=False)


class DownloadRequestSerializer(serializers.Serializer):
    """下载请求序列化器"""
    avid = serializers.CharField(max_length=50)


class SourceCookieSerializer(serializers.Serializer):
    """设置源Cookie请求序列化器"""
    source = serializers.CharField(max_length=50)
    cookie = serializers.CharField()
