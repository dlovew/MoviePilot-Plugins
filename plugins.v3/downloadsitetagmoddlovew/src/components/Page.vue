<script setup>
/**
 * 数据页（联邦 ./Page）。
 *
 * V3 宿主在 render_mode=vue 时固定加载 ./Page，插件若不暴露该组件，
 * 数据页就会显示「无法加载组件」。这里提供插件运行状态概览，并保留
 * 切换到设置页的入口。插件 ID 一律使用宿主注入的实例 ID，支持分身。
 */
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  api: { type: [Object, Function], required: true },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  show_switch: { type: Boolean, default: true },
})

const emit = defineEmits(['close', 'switch', 'action', 'layout'])

const loading = ref(false)
const refreshing = ref(false)
const error = ref('')
const actionMessage = ref('')
const status = ref(null)
const pluginId = computed(() => props.pluginId || props.sourcePluginId || '')

const episodeTagText = computed(() => {
  const value = status.value?.episode_tag
  if (!value) return '-'
  const separator = value.separator === '' ? '（空）' : String(value.separator)
  return `${value.prefix} / 阈值 ${value.threshold} / 分隔符 ${separator}`
})

const scheduleText = computed(() => {
  const value = status.value
  if (!value) return '-'
  if (value.interval === '计划任务') return `计划任务 · ${value.interval_cron}`
  if (value.interval === '固定间隔') return `固定间隔 · 每 ${value.interval_time} ${value.interval_unit}`
  return value.interval || '禁用'
})

const featureList = computed(() => Object.entries(status.value?.features || {}))

async function loadStatus() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法读取运行状态'
    return
  }
  loading.value = true
  error.value = ''
  try {
    status.value = await props.api.get(`plugin/${pluginId.value}/status`)
  } catch (err) {
    error.value = err?.message || '读取插件状态失败'
  } finally {
    loading.value = false
  }
}

async function refreshEpisodeTags() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法补全集数标签'
    return
  }
  refreshing.value = true
  actionMessage.value = ''
  error.value = ''
  try {
    const response = await props.api.get(`plugin/${pluginId.value}/refresh_episode_tags`)
    actionMessage.value = response?.message || '已开始补全集数标签，请查看插件日志'
  } catch (err) {
    error.value = err?.message || '补全集数标签失败'
  } finally {
    refreshing.value = false
  }
}

onMounted(() => {
  emit('layout', { maxWidth: '52rem' })
  void loadStatus()
})
</script>

<template>
  <div class="plugin-page">
    <v-card>
      <v-card-item>
        <template #append>
          <v-btn v-if="show_switch" color="primary" variant="text" prepend-icon="mdi-cog" @click="emit('switch')">
            设置
          </v-btn>
          <v-btn icon variant="text" @click="emit('close')">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </template>
        <v-card-title>下载任务分类与标签 · 运行状态</v-card-title>
      </v-card-item>

      <v-card-text>
        <v-alert v-if="error" type="warning" class="mb-4">{{ error }}</v-alert>
        <v-alert v-if="actionMessage" type="success" variant="tonal" class="mb-4">{{ actionMessage }}</v-alert>
        <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-4" />

        <template v-if="status">
          <v-row dense>
            <v-col cols="12" sm="6">
              <v-list-item title="插件状态" :subtitle="status.enabled ? '已启用' : '未启用'">
                <template #prepend>
                  <v-icon :color="status.enabled ? 'success' : 'grey'">
                    {{ status.enabled ? 'mdi-check-circle' : 'mdi-pause-circle' }}
                  </v-icon>
                </template>
              </v-list-item>
            </v-col>
            <v-col cols="12" sm="6">
              <v-list-item title="定时策略" :subtitle="scheduleText">
                <template #prepend><v-icon color="primary">mdi-clock-outline</v-icon></template>
              </v-list-item>
            </v-col>
          </v-row>

          <v-divider class="my-3" />
          <div class="text-subtitle-2 mb-2">已启用功能</div>
          <div class="d-flex flex-wrap mb-4">
            <v-chip
              v-for="[name, enabled] in featureList"
              :key="name"
              class="ma-1"
              :color="enabled ? 'primary' : undefined"
              :variant="enabled ? 'flat' : 'outlined'"
              size="small"
            >
              <v-icon start>{{ enabled ? 'mdi-check' : 'mdi-close' }}</v-icon>
              {{ name }}
            </v-chip>
          </div>

          <div class="text-caption text-medium-emphasis mb-3">
            集数标签格式：{{ episodeTagText }}
          </div>

          <v-divider class="my-3" />
          <v-row dense>
            <v-col cols="12" sm="4">
              <div class="text-caption text-medium-emphasis">已选下载器</div>
              <div class="text-body-2">{{ (status.selected_downloaders || []).join('、') || '未选择' }}</div>
            </v-col>
            <v-col cols="12" sm="4">
              <div class="text-caption text-medium-emphasis">可用下载器</div>
              <div class="text-body-2">{{ (status.downloaders || []).join('、') || '无' }}</div>
            </v-col>
            <v-col cols="12" sm="4">
              <div class="text-caption text-medium-emphasis">二级分类</div>
              <div class="text-body-2">{{ status.category_count }} 项 · {{ status.rename_type }}</div>
            </v-col>
          </v-row>

          <v-alert type="info" variant="tonal" density="compact" class="mt-4">
            配置、二级分类重命名与 Tracker 映射请在「设置」页调整；修改后由定时服务或一次性任务生效。
          </v-alert>
        </template>
        <div v-else-if="!loading && !error" class="text-body-2">暂无运行状态数据。</div>
      </v-card-text>

      <v-card-actions>
        <v-btn
          color="primary"
          variant="tonal"
          prepend-icon="mdi-tag-multiple"
          :loading="refreshing"
          @click="refreshEpisodeTags"
        >
          补全集数标签
        </v-btn>
        <v-spacer />
        <v-btn variant="text" prepend-icon="mdi-refresh" @click="loadStatus">刷新</v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>
