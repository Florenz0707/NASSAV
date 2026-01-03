import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { settingsApi } from '../api'

export const useSettingsStore = defineStore('settings', () => {
	// 是否显示女优头像
	const showActorAvatar = ref(true)

	// 显示哪个标题字段：original_title | source_title | translated_title
	const displayTitle = ref('translated_title')

	// 是否已加载后端配置
	const loaded = ref(false)

	// 从后端加载设置
	async function loadSettings() {
		try {
			const response = await settingsApi.get()
			const data = response.data || {}

			// 后端返回的 enable_avatar 是字符串 "true"/"false"
			if (data.enable_avatar !== undefined) {
				showActorAvatar.value = data.enable_avatar === 'true'
			}
			if (data.display_title) {
				displayTitle.value = data.display_title
			}
			loaded.value = true
		} catch (err) {
			console.error('加载用户设置失败:', err)
			// 失败时使用默认值
			loaded.value = true
		}
	}

	// 保存设置到后端
	async function saveSettings() {
		if (!loaded.value) return // 还未加载完成时不保存

		try {
			await settingsApi.update({
				enable_avatar: showActorAvatar.value ? 'true' : 'false',
				display_title: displayTitle.value
			})
		} catch (err) {
			console.error('保存用户设置失败:', err)
		}
	}

	// 监听变化并保存到后端
	watch(
		[showActorAvatar, displayTitle],
		() => {
			saveSettings()
		},
		{ deep: true }
	)

	return {
		showActorAvatar,
		displayTitle,
		loadSettings
	}
})
