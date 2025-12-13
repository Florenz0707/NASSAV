<template>
    <div class="detail-container" v-if="video">
        <div class="header">
            <h1>{{ video.title }}</h1>
            <p class="release-date">发行日期: {{ video.releaseDate }}</p>
        </div>

        <div class="content">
            <div class="poster">
                <img :src="video.poster" :alt="video.title">
            </div>

            <Gallery :images="video.fanarts" />
        </div>
    </div>
</template>

<script>
import Gallery from '../components/Gallery.vue'
import videosApi from '../api/videos'

export default {
    components: { Gallery },
    props: ['id'],
    data() {
        return {
            video: null
        }
    },
    async created() {
        this.video = await videosApi.getVideoDetail(this.id)
    }
}
</script>

<style scoped>
.detail-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 2rem;
  background: white;
  border-radius: 16px;
  box-shadow: 0 5px 30px rgba(255, 107, 139, 0.1);
}

.header h1 {
  color: var(--text-color);
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.release-date {
  color: #ff6b8b;
  font-size: 1rem;
  margin-bottom: 2rem;
}

.poster img {
  width: 100%;
  max-height: 500px;
  object-fit: contain;
  border-radius: 12px;
  box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
}

.video-player {
  margin-top: 2rem;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 5px 25px rgba(0, 0, 0, 0.1);
}
</style>
