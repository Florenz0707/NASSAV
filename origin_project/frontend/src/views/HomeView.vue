<template>
    <div class="container">
        <h1>我的小姐姐</h1>
        <div class="video-grid">
            <VideoCard v-for="video in videos" :key="video.id" :video="video" @click="navigateToDetail(video.id)" />
        </div>
    </div>
</template>

<script>
import VideoCard from '../components/VideoCard.vue'
import videosApi from '../api/videos'

export default {
    name: 'HomeView', // 必须声明name用于keep-alive匹配
    components: { VideoCard },
    data() {
        return {
            videos: [],
            scrollPosition: 0
        }
    },
    async created() {
        // 从缓存恢复数据或重新加载
        if (!this.videos.length) {
            this.videos = await videosApi.getVideoList()
        }
    },
    activated() {
        // 从详情页返回时恢复滚动位置
        window.scrollTo(0, this.scrollPosition)
        },
        beforeRouteLeave(to, from, next) {
        // 离开时保存滚动位置
        this.scrollPosition = window.scrollY
        next()
    },
    methods: {
        navigateToDetail(id) {
            this.$router.push({ name: 'detail', params: { id } })
        }
    }
}
</script>

<style scoped>
.container {
  padding: 2rem;
}

h1 {
  color: var(--text-color);
  margin-bottom: 1.5rem;
  font-weight: 600;
  position: relative;
  display: inline-block;
}

h1::after {
  content: '';
  position: absolute;
  bottom: -8px;
  left: 0;
  width: 50px;
  height: 3px;
  background: var(--secondary-color);
}

.video-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 25px;
  padding: 20px 0;
}
</style>
