import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export const useNotificationsStore = defineStore('notifications', () => {
  const events = ref([]),
    opened = ref(false)
  const unreadCount = computed(() => events.value.filter((event) => event.unread).length)
  function record(event) {
    if (!event?.id || events.value.some((existing) => existing.id === event.id)) return
    events.value = [{ ...event, timestamp: Date.now(), unread: true }, ...events.value].slice(
      0,
      100
    )
  }
  function markRead(id) {
    const event = events.value.find((item) => item.id === id)
    if (event) event.unread = false
  }
  function readAll() {
    events.value.forEach((event) => {
      event.unread = false
    })
  }
  function reset() {
    events.value = []
    opened.value = false
  }
  return {
    events,
    opened,
    unreadCount,
    record,
    markRead,
    readAll,
    reset,
    show: () => {
      opened.value = true
    },
    close: () => {
      opened.value = false
    },
  }
})
