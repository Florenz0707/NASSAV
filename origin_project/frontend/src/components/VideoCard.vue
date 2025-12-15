<template>
    <div class="video-card" @click="$emit('click')">
        <div class="poster-container">
            <img class="poster" :src="video.poster" :alt="video.title">
        </div>
        <div class="info">
            <h3>{{ video.title }}</h3>
        </div>
    </div>
</template>

<script>
export default {
    props: {
        video: {
            type: Object,
            required: true
        }
    }
}
</script>

<style scoped>
.video-card {
    cursor: pointer;
    transition: all 0.3s ease;
    background: white;
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    width: 100%; /* 确保宽度自适应 */
}

.video-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 5px 15px rgba(0, 0, 0, 0.2);
}

/* 9:16 比例容器 */
.poster-container {
    position: relative;
    width: 100%;
    padding-top: 137.78%; /* 9:16比例 (9÷16=0.5625, 1÷0.5625≈1.7778) */
    overflow: hidden;
}

.poster {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
}

.info {
    padding: 12px;
    background: white;
}

h3 {
    margin: 0;
    font-size: 14px;
    font-weight: 500;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: #333;
}
</style>
