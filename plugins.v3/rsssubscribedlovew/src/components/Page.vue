<script setup>
/**
 * 自定义订阅番剧魔改版 —— V3 联邦数据页（./Page）。
 *
 * 数据通过实例作用域的 /runtime_data 读取；所有按钮沿用后端既有 GET 端点，
 * 参数拼在 query 上，操作完成后自行刷新，不依赖宿主的整页重载。
 * onMounted 声明宿主弹窗宽度，只影响本插件。
 */
import { computed, onMounted, reactive, ref } from 'vue'

const props = defineProps({
  api: { type: [Object, Function], required: true },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
  show_switch: { type: Boolean, default: true },
  nativeSubscribe: { type: [Object, Function], default: null },
})

const emit = defineEmits(['close', 'switch', 'action', 'layout'])

const data = ref(null)
const loading = ref(false)
const busy = ref(false)
const error = ref('')

const showAllHistory = ref(false)
const historyFilter = ref('')
const groupSelections = reactive({})

const pluginId = computed(() => props.pluginId || props.sourcePluginId || '')
const waiting = computed(() => data.value?.pending || [])
const groupPending = computed(() => waiting.value.filter(
  item => item.group_status === 'mismatch' && !item.episode_group
))
const history = computed(() => data.value?.history || [])
const retry = computed(() => data.value?.retry || [])
const config = computed(() => data.value?.config || {})
const lastRun = computed(() => data.value?.last_run || {})

const historyFilters = [
  { label: '全部', value: '' },
  { label: '已订阅', value: 'subscribed' },
  { label: '失败', value: 'failed' },
  { label: '忽略', value: 'ignored' },
  { label: '预览', value: 'dry_run' },
]

const matchedHistory = computed(() => historyFilter.value
  ? history.value.filter(item => String(item.action || '') === historyFilter.value)
  : history.value)
const shownHistory = computed(() => matchedHistory.value.slice(0, showAllHistory.value ? 200 : 10))

function tmdbUrl(id) {
  const value = String(id || '').trim()
  return /^\d+$/.test(value) ? `https://www.themoviedb.org/tv/${value}` : ''
}

function sizeText(value) {
  return typeof value === 'number' && isFinite(value)
    ? `${(value / 1024 ** 3).toFixed(2)} GiB/集`
    : '体积未知'
}

function platformChips(candidates) {
  const grouped = new Map()
  for (const candidate of candidates || []) {
    const platform = String(candidate.platform_token || candidate.platform || '').trim()
    const team = String(candidate.team || '').trim()
    const unknown = !platform || platform.toUpperCase() === 'UNKNOWN'
    const label = platform && team ? `${platform}-${team}` : (platform || team || '未知平台')
    const size = typeof candidate.normalized_size === 'number' ? candidate.normalized_size : null
    const current = grouped.get(label)
    if (!current || (size !== null && (current.size === null || size < current.size))) {
      grouped.set(label, { label, unknown, size, title: String(candidate.title || '') })
    }
  }
  return [...grouped.values()].slice(0, 8)
}

function unknownTitles(item) {
  return platformChips(item?.candidates)
    .filter(chip => chip.unknown && chip.title)
    .map(chip => chip.title)
    .slice(0, 3)
}

function groupItems(item) {
  return (item.group_candidates || []).map(group => {
    const meta = [
      group.type_label,
      group.group_count ? `${group.group_count} 季` : '',
      group.episode_count ? `${group.episode_count} 集` : '',
      group.season_episodes ? `该季 ${group.season_episodes} 集` : '',
    ].filter(Boolean).join(' · ')
    return {
      title: `${group.name || group.id}${meta ? ' · ' + meta : ''} · ID ${group.id}`,
      value: String(group.id),
    }
  })
}

function statusLabel(item) {
  return item.group_status === 'mismatch' && !item.episode_group
    ? '待选剧集组' : '等待窗口到期'
}

async function loadData() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法读取运行状态'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const res = await props.api.get(`plugin/${pluginId.value}/runtime_data`)
    data.value = res?.data && !Array.isArray(res) ? res.data : res
  } catch (err) {
    error.value = err?.message || '读取运行状态失败'
  } finally {
    loading.value = false
  }
}

async function callApi(path, params = {}) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
    ).toString()
    const url = `plugin/${pluginId.value}/${path}${query ? '?' + query : ''}`
    await props.api.get(url)
    emit('action')
    await loadData()
  } catch (err) {
    error.value = err?.message || '操作失败'
  } finally {
    busy.value = false
  }
}

async function applyGroup(key) {
  const groupId = groupSelections[key]
  if (!groupId) return
  await callApi('set_episode_group', { key, group_id: groupId })
}

function onCopyFocus(event) {
  event.target.select()
}

onMounted(() => {
  emit('layout', { maxWidth: '60rem' })
  void loadData()
})
</script>

<template>
  <div class="rss-page">
    <v-alert v-if="error" type="warning" variant="tonal" density="compact" class="mb-3">{{ error }}</v-alert>
    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-3" />

    <!-- 运行状态 -->
    <v-card variant="tonal" rounded="lg" class="pa-3 mb-4">
      <div class="rss-status text-body-2 text-center">
        v{{ data?.version || '-' }}　最近运行 {{ lastRun.time || '尚未运行' }}　入池 {{ lastRun.ingested || 0 }}　结算 {{ lastRun.settled || 0 }}　窗口 {{ config.collect_window_hours || 24 }}h　{{ config.dry_run ? '试运行' : '正常' }}<span v-if="lastRun.reidentified">　重识别 {{ lastRun.reidentified }}</span>
      </div>
      <div class="rss-metrics">
        <v-chip size="small" color="primary" variant="flat">等待中 {{ waiting.length }}</v-chip>
        <v-chip size="small" :color="groupPending.length ? 'warning' : 'grey'" variant="flat">待选剧集组 {{ groupPending.length }}</v-chip>
        <v-chip size="small" :color="retry.length ? 'error' : 'grey'" variant="flat">待重试 {{ retry.length }}</v-chip>
        <v-chip size="small" color="grey" variant="flat">已处理 {{ data?.handled_count || 0 }}</v-chip>
      </div>
      <v-card-actions class="justify-center">
        <v-btn size="small" color="primary" variant="tonal" :disabled="busy" @click="callApi('run_check')">刷新全部 RSS</v-btn>
        <v-btn size="small" color="primary" variant="tonal" :disabled="busy" @click="callApi('settle')">结算全部候选</v-btn>
        <v-btn v-if="show_switch" size="small" variant="text" prepend-icon="mdi-cog" @click="emit('switch')">设置</v-btn>
        <v-btn icon size="small" variant="text" @click="emit('close')"><v-icon>mdi-close</v-icon></v-btn>
      </v-card-actions>
    </v-card>

    <!-- 待选择剧集组：vue 模式下可以用真正的下拉 -->
    <section v-if="groupPending.length" class="rss-section">
      <div class="rss-section-title">待选择剧集组（{{ groupPending.length }}）</div>
      <v-card v-for="item in groupPending" :key="item.key" variant="tonal" color="warning" rounded="lg" class="pa-3 mb-2">
        <div class="rss-header">
          <a v-if="tmdbUrl(item.tmdbid)" :href="tmdbUrl(item.tmdbid)" target="_blank" rel="noopener noreferrer" class="rss-title-link">{{ item.title || item.key }} ↗</a>
          <span v-else class="rss-title">{{ item.title || item.key }}</span>
          <div class="rss-actions">
            <v-btn size="small" variant="text" color="grey" :disabled="busy" @click="callApi('ignore_group', { key: item.key })">忽略</v-btn>
          </div>
        </div>
        <div class="rss-line">
          {{ item.resource_season_text || '-' }} → TMDB {{ item.main_seasons_text || '-' }}　候选组 {{ (item.group_candidates || []).length }} 个　入池 {{ item.first_seen || '-' }}
        </div>
        <div class="rss-group-pick">
          <v-select v-model="groupSelections[item.key]" :items="groupItems(item)"
                    label="选择剧集组" density="compact" hide-details clearable />
          <v-btn size="small" color="primary" variant="tonal" :disabled="busy || !groupSelections[item.key]"
                 @click="applyGroup(item.key)">选用并结算</v-btn>
          <a v-if="tmdbUrl(item.tmdbid)" :href="tmdbUrl(item.tmdbid) + '/episodes'" target="_blank"
             rel="noopener noreferrer" class="rss-sub-link">季集 / 剧集组 ↗</a>
        </div>
        <div v-if="!groupItems(item).length" class="rss-line">无候选组，可在设置页「剧集组覆盖」按 媒体ID=组ID 填写后刷新，或忽略</div>
      </v-card>
    </section>

    <!-- 等待中 -->
    <section class="rss-section">
      <div class="rss-section-title">等待中（{{ waiting.length }}）</div>
      <v-card v-for="item in waiting" :key="item.key" variant="tonal" rounded="lg" class="pa-3 mb-2">
        <div class="rss-row">
          <v-img v-if="item.poster" :src="item.poster" width="64" aspect-ratio="2/3" cover
                 class="rounded-lg rss-poster" />
          <div v-else class="rss-poster-placeholder" />
          <div class="rss-row-body">
            <div class="rss-header">
              <a v-if="tmdbUrl(item.tmdbid)" :href="tmdbUrl(item.tmdbid)" target="_blank" rel="noopener noreferrer" class="rss-title-link">{{ item.title || item.key }} ↗</a>
              <span v-else class="rss-title">{{ item.title || item.key }}</span>
              <div class="rss-actions">
                <v-btn size="small" color="primary" variant="tonal" :disabled="busy" @click="callApi('settle', { key: item.key })">立即结算</v-btn>
                <v-btn size="small" variant="text" color="grey" :disabled="busy" @click="callApi('ignore_key', { key: item.key })">忽略</v-btn>
              </div>
            </div>
            <div class="rss-line">
              {{ item.resource_season_text || '-' }}　入池 {{ item.first_seen || '-' }}　共 {{ (item.candidates || []).length }} 个候选　{{ statusLabel(item) }}
            </div>
            <div class="rss-chips">
              <v-chip v-for="chip in platformChips(item.candidates)" :key="chip.label" size="small"
                      :color="chip.unknown ? 'warning' : 'primary'"
                      :variant="chip.unknown ? 'flat' : 'tonal'">
                {{ chip.unknown ? '⚠ ' : '' }}{{ chip.label }} · {{ sizeText(chip.size) }}
              </v-chip>
              <span v-if="!platformChips(item.candidates).length" class="rss-line">暂无候选</span>
            </div>
            <div v-if="unknownTitles(item).length" class="rss-copy">
              <div class="rss-line">未识别平台：点击下面标题即可选中复制缩写，填到设置页「自定义平台缩写」</div>
              <input v-for="(title, index) in unknownTitles(item)" :key="index" :value="title" readonly
                     class="rss-copy-input" @focus="onCopyFocus" />
            </div>
          </div>
        </div>
      </v-card>
      <div v-if="!waiting.length" class="rss-empty">暂无等待中的资源</div>
    </section>

    <!-- 识别失败待重试 -->
    <section class="rss-section">
      <div class="rss-section-title">识别失败待重试（{{ retry.length }}）</div>
      <div class="rss-chips">
        <v-chip v-for="(item, index) in retry.slice(0, 30)" :key="index" size="small" variant="tonal">
          {{ item.title || '-' }}（重试 {{ item.attempts || 0 }} 次）
        </v-chip>
        <span v-if="!retry.length" class="rss-empty">无</span>
      </div>
    </section>

    <!-- 决策记录 -->
    <section class="rss-section">
      <div class="rss-section-title">
        决策记录（{{ showAllHistory ? '全部' : '最近' }} {{ shownHistory.length }} / 共 {{ matchedHistory.length }}）
        <span v-if="historyFilter" class="rss-filter-note">· 已筛选 {{ historyFilter }}</span>
      </div>
      <div class="rss-chips rss-filters">
        <v-chip v-for="item in historyFilters" :key="item.value" size="small"
                :color="historyFilter === item.value ? 'primary' : 'grey'"
                :variant="historyFilter === item.value ? 'flat' : 'tonal'"
                @click="historyFilter = item.value">{{ item.label }}</v-chip>
        <v-chip v-if="matchedHistory.length > 10" size="small" variant="tonal"
                @click="showAllHistory = !showAllHistory">{{ showAllHistory ? '收起' : '展开全部' }}</v-chip>
      </div>
      <v-card v-for="record in shownHistory" :key="record.id || record.time" variant="tonal" rounded="lg" class="pa-3 mb-2">
        <div class="rss-row">
          <v-img v-if="record.poster" :src="record.poster" width="64" aspect-ratio="2/3" cover
                 class="rounded-lg rss-poster" />
          <div v-else class="rss-poster-placeholder" />
          <div class="rss-row-body">
            <div class="rss-header">
              <a v-if="tmdbUrl(record.tmdbid)" :href="tmdbUrl(record.tmdbid)" target="_blank" rel="noopener noreferrer" class="rss-title-link">{{ record.title || record.key || '-' }} ↗</a>
              <span v-else class="rss-title">{{ record.title || record.key || '-' }}</span>
              <div class="rss-actions">
                <v-btn size="small" variant="text" color="error" :disabled="busy"
                       @click="callApi('delete_history', { key: record.id || '' })">删除</v-btn>
              </div>
            </div>
            <div class="rss-line">
              {{ record.resource_season_text || '' }}　{{ record.time || '-' }}　{{ record.action || '-' }}　{{ record.platform || '' }}　{{ record.reason || record.error || '' }}
            </div>
          </div>
        </div>
      </v-card>
      <div v-if="!shownHistory.length" class="rss-empty">暂无决策记录</div>
    </section>
  </div>
</template>

<style scoped>
.rss-page {
  width: 100%;
  box-sizing: border-box;
}
.rss-section {
  margin-bottom: 1.25rem;
}
.rss-section-title {
  font-size: 0.875rem;
  font-weight: 600;
  opacity: 0.75;
  margin-bottom: 0.5rem;
}
.rss-filter-note {
  font-weight: 400;
}
.rss-status {
  opacity: 0.8;
}
.rss-metrics,
.rss-chips,
.rss-filters {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.25rem 0.5rem;
  margin-top: 0.5rem;
}
.rss-row {
  display: flex;
  align-items: flex-start;
  gap: 0.875rem;
}
.rss-poster {
  flex: 0 0 auto;
}
.rss-poster-placeholder {
  flex: 0 0 64px;
  width: 64px;
  height: 96px;
  border-radius: 8px;
  background: rgba(128, 128, 128, 0.12);
}
.rss-row-body {
  flex: 1 1 auto;
  min-width: 0;
}
.rss-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.rss-actions {
  display: flex;
  align-items: center;
  gap: 0.25rem;
}
.rss-title {
  font-size: 1rem;
  font-weight: 600;
}
.rss-title-link {
  font-size: 1rem;
  font-weight: 600;
  text-decoration: none;
}
.rss-sub-link {
  font-size: 0.75rem;
  text-decoration: none;
  align-self: center;
}
.rss-line {
  font-size: 0.75rem;
  opacity: 0.75;
  margin-top: 0.25rem;
  word-break: break-word;
}
.rss-group-pick {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  margin-top: 0.5rem;
}
.rss-copy {
  margin-top: 0.5rem;
}
.rss-copy-input {
  display: block;
  width: 100%;
  box-sizing: border-box;
  margin-top: 0.25rem;
  padding: 0.25rem 0.5rem;
  border: 0;
  border-bottom: 1px dashed rgba(128, 128, 128, 0.4);
  background: transparent;
  color: inherit;
  font-size: 0.75rem;
  cursor: text;
  user-select: text !important;
}
.rss-empty {
  font-size: 0.75rem;
  opacity: 0.6;
  padding: 0.5rem 0;
}
</style>
