/**
 * 字体配置
 * 管理应用中可用的字体列表
 */

export const AVAILABLE_FONTS = [
	{
		value: 'Mplus2',
		label: 'Mplus2',
		isDefault: true
	},
	{
		value: 'TheWriteRight',
		label: 'TheWriteRight',
		isDefault: false
	},
	{
		value: 'ZenKakuGothicNew',
		label: 'ZenKakuGothicNew',
		isDefault: false
	}
]

/**
 * 获取默认字体
 */
export function getDefaultFont() {
	const defaultFont = AVAILABLE_FONTS.find(font => font.isDefault)
	return defaultFont ? defaultFont.value : AVAILABLE_FONTS[0].value
}

/**
 * 检查字体是否可用
 */
export function isFontAvailable(fontValue) {
	return AVAILABLE_FONTS.some(font => font.value === fontValue)
}
