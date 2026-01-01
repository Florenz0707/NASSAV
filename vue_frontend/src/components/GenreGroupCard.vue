<template>
	<div class="genre-card" @click="$emit('click')">
		<div class="genre-icon">
			<div class="icon-circle" :style="{ backgroundColor: bgColor }">
				<span class="icon-text">{{ iconText }}</span>
			</div>
		</div>
		<div class="genre-name">{{ genre.name }}</div>
		<div class="genre-count">共有 {{ genre.resource_count }} 部作品</div>
	</div>
</template>

<script>
export default {
	name: 'GenreGroupCard',
	props: {
		genre: {type: Object, required: true}
	},
	computed: {
		iconText() {
			const n = this.genre && this.genre.name ? this.genre.name.trim() : ''
			return n ? n.substring(0, 2) : '类别'
		},
		bgColor() {
			return '#1f2937'
		}
	}
}
</script>

<style scoped>
.genre-card {
	display: flex;
	flex-direction: column;
	align-items: center;
	justify-content: flex-start;
	padding: 12px;
	border-radius: 8px;
	cursor: pointer;
	background: transparent;
	transition: transform 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease;
}

.genre-icon {
	margin-bottom: 10px;
}

.icon-circle {
	width: 72px;
	height: 72px;
	border-radius: 50%;
	display: flex;
	align-items: center;
	justify-content: center;
	color: white;
	font-weight: 500;
	font-size: 24px
}

.genre-name {
	font-weight: 600;
	margin-bottom: 6px;
	text-align: center;
}

.genre-count {
	color: #9ca3af;
	font-size: 13px;
	text-align: center;
}

.genre-card:hover {
	transform: translateY(-6px);
	box-shadow: 0 8px 24px rgba(15, 23, 42, 0.45);
	background-color: rgba(255, 255, 255, 0.02);
}
</style>
