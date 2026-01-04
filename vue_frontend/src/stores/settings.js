import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settingsApi } from '../api'

export const useSettingsStore = defineStore('settings', () => {
	// 是否显示女优头像
	const showActorAvatar = ref(true)

	// 显示哪个标题字段：original_title | source_title | translated_title
	const displayTitle = ref('translated_title')

	// 从后端加载设置（仅在应用启动时调用一次）
	async function loadSettings() {
		try {
			const response = await settingsApi.get()
			const data = response.data || {}

			// 后端返回的 enable_avatar 是字符串 "true"/"false"
			if (data.enable_avatar !== undefined) {
				showActorAvatar.value = data.enable_avatar === 'true'
			}
			if (data.display_title !== undefined) {
				displayTitle.value = data.display_title
			}
		} catch (err) {
			console.error('加载用户设置失败:', err)
			// 失败时使用默认值
		}
	}

	// 保存设置到后端（仅在用户手动点击保存按钮时调用）
	async function saveSettings() {
		try {
			await settingsApi.update({
				enable_avatar: showActorAvatar.value ? 'true' : 'false',
				display_title: displayTitle.value
			})
			return { success: true }
		} catch (err) {
			console.error('保存用户设置失败:', err)
			throw err
		}
	}

	return {
		showActorAvatar,
		displayTitle,
		loadSettings,
		saveSettings
	}
})
