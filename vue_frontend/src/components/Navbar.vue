<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const showResourcesMenu = ref(false)
const showMobileMenu = ref(false)

const resourcesMenuItems = [
	{ path: '/resources', name: '全部资源', icon: 'grid' },
	{ path: '/resources/actors', name: '按演员', icon: 'users' },
	{ path: '/resources/genres', name: '按类别', icon: 'tag' }
]

const isActive = (path) => {
	if (path === '/') return route.path === '/'
	if (path === '/resources') return route.path === '/resources'
	return route.path.startsWith(path)
}

const isResourcesActive = () => {
	return route.path.startsWith('/resources') || route.path.startsWith('/actors') || route.path.startsWith('/genres')
}

const goToResources = () => {
	router.push('/resources')
}

function handleKeydown(e) {
	if (e.key === 'Escape') {
		showResourcesMenu.value = false
		showMobileMenu.value = false
	}
}

onMounted(() => document.addEventListener('keydown', handleKeydown))
onUnmounted(() => document.removeEventListener('keydown', handleKeydown))

// Close menus on route change
watch(() => route.path, () => {
	showMobileMenu.value = false
	showResourcesMenu.value = false
})
</script>

<template>
	<nav class="navbar">
		<div class="navbar-inner">
			<!-- Logo -->
			<RouterLink to="/" class="navbar-logo">
				<span class="logo-icon">
					<svg viewBox="0 0 20 20" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
						<path d="M6.3 4.2a1 1 0 0 1 1.5-.87l8 4.8a1 1 0 0 1 0 1.74l-8 4.8A1 1 0 0 1 6.3 13.8V4.2z"/>
					</svg>
				</span>
				<span class="logo-text">NASSAV</span>
			</RouterLink>

			<!-- Desktop nav links -->
			<div class="nav-links">
				<!-- 首页 -->
				<RouterLink to="/" class="nav-item" :class="{ active: isActive('/') }">
					<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3 9.5L10 3l7 6.5V17a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"/>
						<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 18V13h5v5"/>
					</svg>
					<span class="nav-label">首页</span>
				</RouterLink>

				<!-- 资源库下拉菜单 -->
				<div class="nav-dropdown" @mouseenter="showResourcesMenu = true" @mouseleave="showResourcesMenu = false">
					<button class="nav-item" :class="{ active: isResourcesActive() }" aria-haspopup="menu" :aria-expanded="showResourcesMenu" @click="goToResources">
						<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg">
							<rect x="3" y="3" width="6" height="6" rx="1" stroke-linecap="round" stroke-linejoin="round"/>
							<rect x="11" y="3" width="6" height="6" rx="1" stroke-linecap="round" stroke-linejoin="round"/>
							<rect x="3" y="11" width="6" height="6" rx="1" stroke-linecap="round" stroke-linejoin="round"/>
							<rect x="11" y="11" width="6" height="6" rx="1" stroke-linecap="round" stroke-linejoin="round"/>
						</svg>
						<span class="nav-label">资源库</span>
						<svg class="nav-chevron" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" xmlns="http://www.w3.org/2000/svg">
							<path stroke-linecap="round" stroke-linejoin="round" d="M5 8l5 5 5-5"/>
						</svg>
					</button>

					<div v-if="showResourcesMenu" role="menu" class="dropdown-menu">
						<RouterLink v-for="item in resourcesMenuItems" :key="item.path" :to="item.path"
							class="dropdown-item" :class="{ active: isActive(item.path) }">
							<!-- 全部资源: grid -->
							<svg v-if="item.icon === 'grid'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
								<rect x="3" y="3" width="6" height="6" rx="1"/>
								<rect x="11" y="3" width="6" height="6" rx="1"/>
								<rect x="3" y="11" width="6" height="6" rx="1"/>
								<rect x="11" y="11" width="6" height="6" rx="1"/>
							</svg>
							<!-- 按演员: users -->
							<svg v-else-if="item.icon === 'users'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M13 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM3 17a7 7 0 0 1 14 0"/>
							</svg>
							<!-- 按类别: tag -->
							<svg v-else-if="item.icon === 'tag'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3 3h6l8 8-6 6-8-8V3z"/>
								<circle cx="7" cy="7" r="1" fill="currentColor"/>
							</svg>
							<span>{{ item.name }}</span>
						</RouterLink>
					</div>
				</div>

				<!-- 添加资源 -->
				<RouterLink to="/add" class="nav-item" :class="{ active: isActive('/add') }">
					<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg">
						<circle cx="10" cy="10" r="7" stroke-linecap="round"/>
						<path stroke-linecap="round" stroke-linejoin="round" d="M10 7v6M7 10h6"/>
					</svg>
					<span class="nav-label">添加资源</span>
				</RouterLink>

				<!-- 下载管理 -->
				<RouterLink to="/downloads" class="nav-item" :class="{ active: isActive('/downloads') }">
					<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg">
						<path stroke-linecap="round" stroke-linejoin="round" d="M10 3v10M6 9l4 4 4-4"/>
						<path stroke-linecap="round" d="M3 16h14"/>
					</svg>
					<span class="nav-label">下载管理</span>
				</RouterLink>

				<!-- 设置 -->
				<RouterLink to="/settings" class="nav-item" :class="{ active: isActive('/settings') }">
					<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" xmlns="http://www.w3.org/2000/svg">
						<circle cx="10" cy="10" r="2.5"/>
						<path stroke-linecap="round" stroke-linejoin="round" d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42"/>
					</svg>
					<span class="nav-label">设置</span>
				</RouterLink>
			</div>

			<!-- Hamburger button (mobile only) -->
			<button class="hamburger-btn" :aria-expanded="showMobileMenu" aria-label="菜单" @click="showMobileMenu = !showMobileMenu">
				<svg v-if="!showMobileMenu" class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16M4 18h16"/>
				</svg>
				<svg v-else class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
					<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
				</svg>
			</button>
		</div>

		<!-- Mobile menu -->
		<div v-if="showMobileMenu" class="mobile-menu">
			<RouterLink to="/" class="mobile-nav-item" :class="{ active: isActive('/') }">
				<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 9.5L10 3l7 6.5V17a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"/>
					<path stroke-linecap="round" stroke-linejoin="round" d="M7.5 18V13h5v5"/>
				</svg>
				首页
			</RouterLink>

			<!-- 资源库 group -->
			<div class="mobile-nav-group-label">资源库</div>
			<RouterLink v-for="item in resourcesMenuItems" :key="item.path" :to="item.path"
				class="mobile-nav-item mobile-nav-sub" :class="{ active: isActive(item.path) }">
				<svg v-if="item.icon === 'grid'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<rect x="3" y="3" width="6" height="6" rx="1"/><rect x="11" y="3" width="6" height="6" rx="1"/>
					<rect x="3" y="11" width="6" height="6" rx="1"/><rect x="11" y="11" width="6" height="6" rx="1"/>
				</svg>
				<svg v-else-if="item.icon === 'users'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M13 6a3 3 0 1 1-6 0 3 3 0 0 1 6 0zM3 17a7 7 0 0 1 14 0"/>
				</svg>
				<svg v-else-if="item.icon === 'tag'" class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M3 3h6l8 8-6 6-8-8V3z"/>
					<circle cx="7" cy="7" r="1" fill="currentColor"/>
				</svg>
				{{ item.name }}
			</RouterLink>

			<RouterLink to="/add" class="mobile-nav-item" :class="{ active: isActive('/add') }">
				<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<circle cx="10" cy="10" r="7" stroke-linecap="round"/>
					<path stroke-linecap="round" stroke-linejoin="round" d="M10 7v6M7 10h6"/>
				</svg>
				添加资源
			</RouterLink>

			<RouterLink to="/downloads" class="mobile-nav-item" :class="{ active: isActive('/downloads') }">
				<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<path stroke-linecap="round" stroke-linejoin="round" d="M10 3v10M6 9l4 4 4-4"/>
					<path stroke-linecap="round" d="M3 16h14"/>
				</svg>
				下载管理
			</RouterLink>

			<RouterLink to="/settings" class="mobile-nav-item" :class="{ active: isActive('/settings') }">
				<svg class="nav-icon" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5">
					<circle cx="10" cy="10" r="2.5"/>
					<path stroke-linecap="round" stroke-linejoin="round" d="M10 2v2M10 16v2M2 10h2M16 10h2M4.22 4.22l1.42 1.42M14.36 14.36l1.42 1.42M4.22 15.78l1.42-1.42M14.36 5.64l1.42-1.42"/>
				</svg>
				设置
			</RouterLink>
		</div>
	</nav>
</template>

<style scoped>
.navbar {
	background: var(--bg-overlay);
	border-bottom: 1px solid var(--border-color);
	position: fixed;
	top: 0;
	left: 0;
	right: 0;
	z-index: 100;
	backdrop-filter: blur(12px);
}

.navbar-inner {
	max-width: 1400px;
	margin: 0 auto;
	padding: 0 2rem;
	height: 4rem;
	display: flex;
	align-items: center;
	justify-content: space-between;
}

.navbar-logo {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	text-decoration: none;
	color: var(--text-primary);
	font-weight: 600;
	font-size: 1.25rem;
	letter-spacing: 0.05em;
}

.logo-icon {
	width: 2.25rem;
	height: 2.25rem;
	background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
	border-radius: 10px;
	display: flex;
	align-items: center;
	justify-content: center;
	color: white;
	box-shadow: 0 4px 12px rgba(255, 107, 107, 0.3);
	flex-shrink: 0;
}

.logo-icon svg {
	width: 1rem;
	height: 1rem;
}

.logo-text {
	background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
	-webkit-background-clip: text;
	-webkit-text-fill-color: transparent;
	background-clip: text;
}

.nav-links {
	display: flex;
	gap: 0.25rem;
}

.nav-item {
	display: flex;
	align-items: center;
	gap: 0.5rem;
	padding: 0.625rem 1rem;
	border-radius: 0.5rem;
	text-decoration: none;
	color: var(--text-secondary);
	font-size: 0.875rem;
	font-weight: 500;
	transition: color 0.2s, background 0.2s;
	background: transparent;
	border: none;
	cursor: pointer;
}

.nav-item:hover {
	color: var(--text-primary);
	background: rgba(255, 255, 255, 0.05);
}

.nav-item.active {
	color: var(--accent-primary);
	background: rgba(255, 107, 107, 0.1);
}

.nav-icon {
	width: 1.125rem;
	height: 1.125rem;
	flex-shrink: 0;
}

.nav-label {
	display: none;
}

@media (min-width: 768px) {
	.nav-label {
		display: inline;
	}
}

.nav-chevron {
	width: 0.75rem;
	height: 0.75rem;
	opacity: 0.6;
}

/* Dropdown */
.nav-dropdown {
	position: relative;
}

.dropdown-menu {
	position: absolute;
	top: 100%;
	left: 0;
	background: var(--bg-overlay);
	backdrop-filter: blur(16px);
	border: 1px solid var(--border-color);
	border-radius: 0.5rem;
	box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
	min-width: 120px;
	overflow: hidden;
	z-index: 10;
	padding-top: 0.25rem;
}

.dropdown-item {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 0.625rem 1rem;
	text-decoration: none;
	color: var(--text-secondary);
	font-size: 0.875rem;
	font-weight: 500;
	transition: color 0.2s, background 0.2s;
}

.dropdown-item:hover {
	color: var(--text-primary);
	background: rgba(255, 255, 255, 0.05);
}

.dropdown-item.active {
	color: var(--accent-primary);
	background: rgba(255, 107, 107, 0.1);
}

/* Hamburger button - mobile only */
.hamburger-btn {
	display: none;
	align-items: center;
	justify-content: center;
	padding: 0.5rem;
	border-radius: 0.5rem;
	background: transparent;
	border: none;
	cursor: pointer;
	color: var(--text-primary);
	transition: background 0.2s;
}

.hamburger-btn:hover {
	background: rgba(255, 255, 255, 0.05);
}

/* Mobile menu */
.mobile-menu {
	display: none;
	flex-direction: column;
	padding: 0.5rem;
	border-top: 1px solid var(--border-color);
}

.mobile-nav-item {
	display: flex;
	align-items: center;
	gap: 0.75rem;
	padding: 0.75rem 1rem;
	border-radius: 0.5rem;
	text-decoration: none;
	color: var(--text-secondary);
	font-size: 0.9rem;
	font-weight: 500;
	transition: color 0.2s, background 0.2s;
}

.mobile-nav-item:hover,
.mobile-nav-item.active {
	color: var(--accent-primary);
	background: rgba(255, 107, 107, 0.1);
}

.mobile-nav-group-label {
	padding: 0.5rem 1rem 0.25rem;
	font-size: 0.7rem;
	font-weight: 600;
	color: var(--text-muted);
	text-transform: uppercase;
	letter-spacing: 0.08em;
}

.mobile-nav-sub {
	padding-left: 1.75rem;
}

@media (max-width: 767px) {
	.hamburger-btn {
		display: flex;
	}

	.nav-links {
		display: none;
	}

	.mobile-menu {
		display: flex;
	}

	.navbar-inner {
		padding: 0 1rem;
	}
}

@media (max-width: 480px) {
	.navbar-inner {
		padding: 0 1rem;
	}
}
</style>
