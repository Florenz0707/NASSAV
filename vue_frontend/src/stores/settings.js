import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
	// 从 localStorage 加载初始设置
	const savedSettings = JSON.parse(window.localStorage.getItem('nassav-settings') || '{}')

	// 是否显示女优头像
	const showActorAvatar = ref(savedSettings.showActorAvatar !== undefined ? savedSettings.showActorAvatar : true)

	// 监听变化并保存到 localStorage
	watch(
		[showActorAvatar],
		() => {
			window.localStorage.setItem('nassav-settings', JSON.stringify({
				showActorAvatar: showActorAvatar.value
			}))
		},
		{ deep: true }
	)

	return {
		showActorAvatar
	}
})
