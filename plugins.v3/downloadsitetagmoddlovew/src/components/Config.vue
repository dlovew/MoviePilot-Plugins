<script setup>
/**
 * 下载任务分类与标签插件的 V3 联邦配置组件。
 *
 * 配置读取只依赖宿主注入的 initialConfig，保存统一通过 emit('save') 交给宿主；
 * 调用插件自定义 API 时使用实例作用域的 pluginId，不硬编码类名，以支持插件分身。
 */
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  api: { type: [Object, Function], required: true },
  initialConfig: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: '' },
  sourcePluginId: { type: String, default: '' },
})

const emit = defineEmits(['save', 'close', 'switch', 'layout'])

const scheduleTypes = ['禁用', '计划任务', '固定间隔']
const intervalUnits = ['分钟', '小时']

const defaultConfig = {
  name: '',
  enable: false,
  interval: '禁用',
  interval_cron: '5 4 * * *',
  interval_time: 6,
  interval_unit: '小时',
  enable_media_tag: false,
  enable_tag: false,
  enable_category: false,
  enable_del_tags: false,
  downloaders: [],
  all_downloaders: [],
  all_cat: [],
  all_cat_rename: [],
  onlyonce: false,
  rename_type: false,
  path_rename: '',
  catprefix: '',
  siteprefix: '',
  tracker_mappings_str: '',
  enable_episode_tag: true,
  episode_tag_prefix: 'E',
  episode_merge_threshold: 2,
  episode_merge_separator: '-',
}

const prefixRules = [
  value => !!String(value ?? '').trim() || '标签前缀必填',
]

const config = reactive({ ...defaultConfig, ...(props.initialConfig || {}) })
const form = ref(null)
const isFormValid = ref(true)
const error = ref(null)
const saving = ref(false)
const pluginId = computed(() => props.pluginId || props.sourcePluginId || config.id || '')

function notifyClose() {
  emit('close')
}

async function saveConfig() {
  if (!isFormValid.value) {
    error.value = '请修正表单错误'
    return
  }
  saving.value = true
  error.value = null
  try {
    // V3 宿主统一 PUT plugin/{id} 保存配置，组件不自行调用配置端点
    emit('save', { ...config })
  } catch (err) {
    error.value = err?.message || '保存配置失败'
  } finally {
    saving.value = false
  }
}

function resetForm() {
  Object.keys(props.initialConfig || {}).forEach(key => {
    config[key] = props.initialConfig[key]
  })
  form.value?.resetValidation?.()
}

async function resetCategories() {
  if (!pluginId.value) {
    error.value = '未获取到插件实例 ID，无法重置二级分类'
    return
  }
  try {
    const response = await props.api.post(`plugin/${pluginId.value}/reset_categories`)
    if (response?.all_cat_rename) {
      config.all_cat_rename = [...response.all_cat_rename]
    }
    if (response?.all_cat) {
      config.all_cat = [...response.all_cat]
    }
    error.value = response?.message || '二级分类已重置'
  } catch (err) {
    error.value = err?.message || '重置二级分类失败'
  }
}
</script>

<template>
  <div class="plugin-config">
    <v-card>
      <v-card-item>
        <template #append>
          <v-btn icon color="primary" variant="text" @click="notifyClose">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </template>
        <v-card-title>{{ config.name }}</v-card-title>
      </v-card-item>

      <v-card-text class="overflow-y-auto">
        <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
        <v-form ref="form" v-model="isFormValid" @submit.prevent="saveConfig">
          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">基本设置</div>
          <v-row>
            <v-col cols="6" md="3">
              <v-switch v-model="config.enable" label="启用插件" color="primary" persistent-hint inset />
            </v-col>
            <v-col cols="6" md="3">
              <v-checkbox v-model="config.enable_tag" label="自动站点标签" color="primary" />
            </v-col>
            <v-col cols="6" md="3">
              <v-checkbox v-model="config.enable_media_tag" label="自动剧名标签" color="primary" />
            </v-col>
            <v-col cols="6" md="3">
              <v-checkbox v-model="config.enable_category" label="自动设置分类" color="primary" />
            </v-col>
            <v-col cols="6" md="6">
              <v-checkbox v-model="config.onlyonce" label="补全下载历史的标签与分类(一次性任务)" color="primary" inset />
            </v-col>
            <v-col cols="6" md="3">
              <v-checkbox v-model="config.enable_del_tags" label="自动删除未使用标签" color="primary" />
            </v-col>
            <v-col>
              <v-switch v-model="config.rename_type" label="自定义" color="primary" persistent-hint inset />
            </v-col>
          </v-row>

          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">集数标签</div>
          <v-row>
            <v-col cols="12" md="3">
              <v-switch
                v-model="config.enable_episode_tag"
                label="下载时自动打集数标签"
                color="primary"
                inset
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="config.episode_tag_prefix"
                label="标签前缀（必填）"
                :rules="prefixRules"
                placeholder="E"
                hint="例如 E -> E01"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model.number="config.episode_merge_threshold"
                label="合并阈值"
                type="number"
                min="0"
                hint="连续集数超过阈值才合并；<= 1 不合并"
                persistent-hint
              />
            </v-col>
            <v-col cols="12" md="3">
              <v-text-field
                v-model="config.episode_merge_separator"
                label="合并分隔符（可空）"
                placeholder="-"
                hint="默认 -，如 E01-03；留空为 E0103"
                persistent-hint
              />
            </v-col>
            <v-col cols="12">
              <v-alert type="info" variant="tonal" density="compact">
                默认前缀 E、阈值 2、分隔符 -：如 E01、E02；连续 3 集及以上合并为 E01-03。
                修改任意格式配置并保存后，会自动全量刷新存量标签并迁移旧格式标签；
                也可在数据页点「补全集数标签」手动执行。
              </v-alert>
            </v-col>
          </v-row>

          <v-divider />

          <v-row>
            <v-col cols="12">
              <v-select
                v-model="config.downloaders"
                :items="config.all_downloaders"
                label="下载器"
                placeholder="请选择下载器"
                item-text="title"
                item-value="value"
                multiple
                chips
              />
            </v-col>
            <v-col cols="6" md="6">
              <v-text-field v-model="config.catprefix" label="自定义分类前缀" placeholder="默认为空" />
            </v-col>
            <v-col cols="6" md="6">
              <v-text-field v-model="config.siteprefix" label="自定义站点标签前缀" placeholder="默认为空" />
            </v-col>
            <v-col cols="6" md="3">
              <v-select v-model="config.interval" :items="scheduleTypes" label="定时任务类型" />
            </v-col>
            <v-col v-if="config.interval === '计划任务'" cols="6" md="6">
              <VCronField
                v-model="config.interval_cron"
                label="计划任务设置 CRON表达式"
                hint="设置日志清理的执行周期，如：5 4 * * * (每天凌晨4:05)"
                persistent-hint
                density="compact"
              />
            </v-col>
            <v-col v-if="config.interval === '固定间隔'" cols="6" md="3">
              <v-text-field
                v-model.number="config.interval_time"
                label="固定间隔"
                type="number"
                placeholder="输入间隔时间"
              />
            </v-col>
            <v-col v-if="config.interval === '固定间隔'" cols="6" md="3">
              <v-select v-model="config.interval_unit" :items="intervalUnits" label="单位" density="compact" />
            </v-col>
          </v-row>

          <v-divider class="my-4" />
          <v-row>
            <v-col cols="12">
              <v-alert type="info" variant="tonal">
                以下为 tracker 映射规则，您可以根据需要修改或添加新的规则。
              </v-alert>
            </v-col>
          </v-row>
          <v-row>
            <v-col cols="12">
              <v-textarea
                v-model="config.tracker_mappings_str"
                label="Tracker域名映射规则"
                rows="6"
                auto-grow
                placeholder="每行一个映射，格式：tracker域名 -> 映射域名&#10;例如：chdbits.xyz -> ptchdbits.co"
                hint="支持的分隔符：->, →, :, ：，空格"
                persistent-hint
              />
            </v-col>
          </v-row>

          <v-divider class="my-4" />
          <v-row v-if="!config.rename_type">
            <v-col cols="12">
              <v-row>
                <v-col v-for="(category, index) in config.all_cat" :key="index" cols="12" md="3">
                  <v-text-field
                    v-model="config.all_cat_rename[index]"
                    :label="category"
                    :placeholder="category"
                  />
                </v-col>
              </v-row>
            </v-col>
          </v-row>
          <v-row v-else>
            <v-col cols="12">
              <v-textarea
                v-model="config.path_rename"
                label="按路径自定义分类"
                hint="每一行一个配置，中间以#分隔：路径#分类名称"
                persistent-hint
                variant="filled"
                auto-grow
              />
            </v-col>
          </v-row>
          <v-divider class="my-4" />
        </v-form>
      </v-card-text>

      <v-card-actions>
        <v-btn color="secondary" @click="resetForm">重置</v-btn>
        <v-btn v-if="!config.rename_type" color="warning" @click="resetCategories">重置二级分类</v-btn>
        <v-spacer />
        <v-btn color="primary" :disabled="!isFormValid" :loading="saving" @click="saveConfig">保存配置</v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>
