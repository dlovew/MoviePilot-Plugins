<script setup>
/**
 * 自定义订阅番剧魔改版 —— V3 联邦配置组件（./Config）。
 *
 * 配置只依赖宿主注入的 initialConfig，保存统一 emit('save') 交给宿主；
 * 平台多选项通过实例作用域的 /platform_options 读取，接口失败时按当前配置兜底。
 * 插件 ID 一律使用宿主注入值，支持分身。
 */
import { computed, onMounted, reactive, ref } from 'vue'

const props = defineProps({
  api: { type: [Object, Function], required: true },
  initialConfig: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
})

const emit = defineEmits(['save', 'close', 'switch', 'layout'])

const defaultConfig = {
  enabled: false,
  notify: false,
  onlyonce: false,
  clear: false,
  proxy: false,
  filter: false,
  cron: '*/30 * * * *',
  collect_window_hours: 24,
  address: '',
  include: '',
  exclude: '',
  size_range: '',
  save_path: '',
  auto_detect_episode_group: true,
  auto_select_single_group: false,
  episode_group_overrides: '',
  pending_group_action: 'notify',
  retry_unrecognized: true,
  notify_unrecognized: true,
  dry_run: false,
  tier1_platforms: [],
  tier2_platforms: [],
  tier3_platforms: [],
  tier2_unconditional: true,
  custom_platforms: '',
}

const config = reactive({ ...defaultConfig, ...(props.initialConfig || {}) })
const platformOptions = ref([])
const optionsError = ref('')
const saving = ref(false)

const pluginId = computed(() => props.pluginId || props.sourcePluginId || '')
const pendingGroupItems = [
  { title: '通知并继续挂起', value: 'notify' },
  { title: '直接忽略', value: 'ignore' },
]

function fallbackOptions() {
  const names = new Set([
    ...(config.tier1_platforms || []),
    ...(config.tier2_platforms || []),
    ...(config.tier3_platforms || []),
    ...String(config.custom_platforms || '').split('\n').map(s => s.trim()).filter(Boolean),
  ])
  return [...names].map(name => ({ title: name, value: name }))
}

async function loadPlatformOptions() {
  optionsError.value = ''
  if (!pluginId.value) {
    platformOptions.value = fallbackOptions()
    return
  }
  try {
    const res = await props.api.get(`plugin/${pluginId.value}/platform_options`)
    const items = Array.isArray(res) ? res : (res?.data || res?.items || [])
    platformOptions.value = Array.isArray(items) && items.length ? items : fallbackOptions()
  } catch (err) {
    optionsError.value = err?.message || '平台选项读取失败，已使用当前配置'
    platformOptions.value = fallbackOptions()
  }
}

function refreshOptions() {
  // 自定义缩写填入后点保存前也能在下拉里看到
  const fromApi = new Set(platformOptions.value.map(item => item.value ?? item.title))
  for (const item of fallbackOptions()) {
    if (!fromApi.has(item.value)) platformOptions.value.push(item)
  }
}

function saveConfig() {
  saving.value = true
  try {
    emit('save', { ...config })
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  emit('layout', { maxWidth: '60rem' })
  void loadPlatformOptions()
})
</script>

<template>
  <div class="rss-config">
    <v-card flat>
      <v-card-item>
        <template #append>
          <v-btn color="primary" variant="text" prepend-icon="mdi-cog" @click="emit('switch')">数据页</v-btn>
          <v-btn icon variant="text" @click="emit('close')">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </template>
        <v-card-title>自定义订阅番剧 · 设置</v-card-title>
      </v-card-item>

      <v-card-text>
        <v-alert v-if="optionsError" type="warning" variant="tonal" density="compact" class="mb-3">
          {{ optionsError }}
        </v-alert>

        <div class="text-subtitle-2 mb-2">基础</div>
        <v-row dense>
          <v-col v-for="item in [
            { key: 'enabled', label: '启用插件' },
            { key: 'notify', label: '发送通知' },
            { key: 'onlyonce', label: '立即运行一次' },
            { key: 'clear', label: '清空候选池与历史' },
            { key: 'proxy', label: '使用代理' },
            { key: 'filter', label: '应用订阅过滤规则' },
          ]" :key="item.key" cols="12" sm="6" md="4">
            <v-switch v-model="config[item.key]" :label="item.label" color="primary" density="compact" hide-details />
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="12" md="6">
            <v-text-field v-model="config.cron" label="执行周期（5 位 cron，留空则每 30 分钟）"
                          placeholder="*/30 * * * *" density="compact" hide-details="auto"
                          hint="例如 0 */6 * * * 表示每 6 小时" persistent-hint />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model.number="config.collect_window_hours" label="候选窗口（小时）"
                          type="number" min="1" density="compact" hide-details />
          </v-col>
        </v-row>

        <v-row dense class="mt-2">
          <v-col cols="12">
            <v-textarea v-model="config.address" label="RSS 链接（每行一个，全部都会处理）"
                        rows="3" auto-grow density="compact" hide-details
                        placeholder="https://...&#10;https://..." />
          </v-col>
          <v-col cols="12" md="6">
            <v-textarea v-model="config.include" label="包含规则（正则，决定哪些资源入池）"
                        rows="2" auto-grow density="compact" hide-details
                        placeholder="(?=.*月新番)(?=.*E01)" />
          </v-col>
          <v-col cols="12" md="6">
            <v-textarea v-model="config.exclude" label="排除规则（正则）"
                        rows="2" auto-grow density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="config.size_range" label="体积范围（GiB，如 0.5-8）"
                          density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-text-field v-model="config.save_path" label="订阅保存目录（留空自动）"
                          density="compact" hide-details />
          </v-col>
        </v-row>

        <div class="text-subtitle-2 mt-5 mb-2">决策</div>
        <v-row dense>
          <v-col v-for="item in [
            { key: 'auto_detect_episode_group', label: '自动探测剧集组' },
            { key: 'auto_select_single_group', label: '唯一候选组自动选用' },
            { key: 'retry_unrecognized', label: '识别失败进入重试队列' },
            { key: 'notify_unrecognized', label: '识别失败发送通知' },
            { key: 'dry_run', label: '试运行（只预览不订阅）' },
          ]" :key="item.key" cols="12" sm="6" md="4">
            <v-switch v-model="config[item.key]" :label="item.label" color="primary" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-select v-model="config.pending_group_action" :items="pendingGroupItems"
                      label="到期未选剧集组" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-textarea v-model="config.episode_group_overrides"
                        label="剧集组覆盖（每行 媒体ID=组ID）" rows="2" auto-grow
                        density="compact" hide-details placeholder="12345=5f3a..." />
          </v-col>
        </v-row>

        <div class="text-subtitle-2 mt-5 mb-2">平台分层</div>
        <v-row dense>
          <v-col cols="12" md="4">
            <v-select v-model="config.tier1_platforms" :items="platformOptions" multiple chips closable-chips
                      label="Tier1 首选平台（按等效单集体积选最小）" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="config.tier2_platforms" :items="platformOptions" multiple chips closable-chips
                      label="Tier2 兜底平台" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="4">
            <v-select v-model="config.tier3_platforms" :items="platformOptions" multiple chips closable-chips
                      label="Tier3 其余兜底平台" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-switch v-model="config.tier2_unconditional" label="Tier2 无条件优先（不与 Tier3 比体积）"
                      color="primary" density="compact" hide-details />
          </v-col>
          <v-col cols="12" md="6">
            <v-textarea v-model="config.custom_platforms" @blur="refreshOptions"
                        label="自定义平台缩写（每行一个，按资源标题里的写法）"
                        rows="2" auto-grow density="compact" hide-details placeholder="ABEMA" />
          </v-col>
        </v-row>

        <v-alert type="info" variant="tonal" density="compact" class="mt-4">
          入池完全由「包含规则」决定，插件不判断季首或合集。识别成功后按「媒体身份 + 季」归并候选，
          窗口从该季第一条入池资源起算；到期按分层规则比较等效单集体积，只创建一次整季订阅。
          平台缩写取自资源标题原文，新增平台先在自定义框填写并保存即可在下拉中勾选。
        </v-alert>
      </v-card-text>

      <v-card-actions class="justify-end">
        <v-btn variant="text" @click="loadPlatformOptions">刷新平台选项</v-btn>
        <v-btn color="primary" variant="tonal" :loading="saving" prepend-icon="mdi-content-save" @click="saveConfig">
          保存
        </v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<style scoped>
.rss-config {
  width: 100%;
  box-sizing: border-box;
}
</style>
