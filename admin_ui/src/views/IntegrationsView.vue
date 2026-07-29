<script setup lang="ts">
import { computed, inject, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";
import { channelLabels, displayLabel, providerLabels } from "../uiLabels";

const user = inject<Ref<any>>("adminUser")!;
const rows = ref<any[]>([]);
const secrets = ref<Record<string, string>>({});
const results = ref<Record<string, any>>({});
const acting = ref("");
const message = ref("");
const channelMeta: Record<string, any> = {
  report_llm: { providers: ["mock", "deepseek", "anthropic", "claude", "openai_compatible"] },
  embedding: { providers: ["openai"] },
  evaluation: { providers: ["openai_compatible"] },
  crossref: { providers: ["crossref"] },
};
const configuredCount = computed(() => rows.value.filter((row) => row.enabled && (row.channel === "crossref" || row.provider === "mock" || row.secret_configured)).length);

async function load() {
  const result = await api<any>("/api/v1/admin/integrations");
  rows.value = (result.integrations || []).map((row: any) => ({ ...row, settings: { ...(row.settings || {}) } }));
}

async function save(row: any) {
  acting.value = `save:${row.channel}`;
  message.value = "";
  try {
    await api(`/api/v1/admin/integrations/${row.channel}`, {
      method: "PUT",
      body: jsonBody({
        provider: row.provider,
        base_url: row.base_url,
        model: row.model,
        timeout_sec: row.timeout_sec,
        max_concurrency: row.max_concurrency,
        enabled: row.enabled,
        settings: row.settings,
      }),
    });
    message.value = `${channelLabels[row.channel]?.title || "服务"}设置已保存。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function saveSecret(row: any) {
  if (!confirm(`${row.secret_configured ? "更换" : "保存"}${channelLabels[row.channel]?.title || "服务"}的访问密钥？保存后不会再次显示。`)) return;
  acting.value = `secret:${row.channel}`;
  try {
    await api(`/api/v1/admin/integrations/${row.channel}/secret`, { method: "PUT", body: jsonBody({ secret: secrets.value[row.channel] }) });
    secrets.value[row.channel] = "";
    message.value = `${channelLabels[row.channel]?.title || "服务"}的访问密钥已安全保存。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function clearSecret(row: any) {
  if (!confirm(`移除${channelLabels[row.channel]?.title || "服务"}的访问密钥？系统会自动切换到安全的备用方式。`)) return;
  acting.value = `secret:${row.channel}`;
  try {
    await api(`/api/v1/admin/integrations/${row.channel}/secret`, { method: "DELETE" });
    message.value = `${channelLabels[row.channel]?.title || "服务"}的访问密钥已移除。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function testConnection(row: any) {
  acting.value = `test:${row.channel}`;
  try {
    results.value[row.channel] = await api(`/api/v1/admin/integrations/${row.channel}/test`, { method: "POST" });
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "—";
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="服务设置" :description="`${configuredCount}/${rows.length || 4} 项服务当前可用。各服务互相独立，不可用时系统会安全降级。`" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="info">连接测试只发送固定的合成文字，不会发送用户测量、对话或知识库全文；访问密钥保存后不会再次显示。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }}</FeedbackBanner>
  <div v-if="loading" class="card loading-panel">正在读取服务状态…</div>

  <div v-else class="integration-grid">
    <section class="card integration-card" v-for="row in rows" :key="row.channel">
      <div class="integration-head">
        <div><span class="service-icon">{{ row.channel === "report_llm" ? "文" : row.channel === "embedding" ? "检" : row.channel === "evaluation" ? "质" : "书" }}</span><h2>{{ channelLabels[row.channel]?.title || row.channel }}</h2><p>{{ channelLabels[row.channel]?.description }}</p></div>
        <StatusBadge :status="row.enabled ? 'active' : 'disabled'" />
      </div>

      <div class="service-summary">
        <div><span>服务方式</span><strong>{{ displayLabel(providerLabels, row.provider) }}</strong></div>
        <div v-if="row.channel !== 'crossref' && row.provider !== 'mock'"><span>访问密钥</span><strong :class="row.secret_configured ? 'success' : 'warning-text'">{{ row.secret_configured ? "已安全保存" : "需要设置" }}</strong></div>
        <div v-else><span>访问方式</span><strong>{{ row.channel === "crossref" ? "公开服务，无需密钥" : "本机运行" }}</strong></div>
      </div>

      <div v-if="user.role === 'admin'" class="toolbar integration-actions">
        <label class="service-switch"><input type="checkbox" v-model="row.enabled" /><span>{{ row.enabled ? "服务已开启" : "服务已关闭" }}</span></label>
        <button class="btn primary-soft" :disabled="!!acting" @click="save(row)">{{ acting === `save:${row.channel}` ? "正在保存…" : "保存状态" }}</button>
        <button class="btn" :disabled="!!acting || !row.enabled" @click="testConnection(row)">{{ acting === `test:${row.channel}` ? "正在测试…" : "测试是否可用" }}</button>
      </div>

      <div v-if="row.channel !== 'crossref'" class="secret-panel">
        <div><strong>访问密钥</strong><StatusBadge :status="row.secret_configured ? 'current' : 'missing'" :label="row.secret_configured ? '已保存' : '未设置'" /><small v-if="row.secret_updated_at">最近更新：{{ formatDate(row.secret_updated_at) }}</small></div>
        <div v-if="user.role === 'admin'" class="toolbar">
          <input class="input" type="password" v-model="secrets[row.channel]" autocomplete="new-password" placeholder="输入新密钥，保存后不会再次显示" />
          <button class="btn" :disabled="!secrets[row.channel] || !!acting" @click="saveSecret(row)">{{ row.secret_configured ? "更换密钥" : "安全保存" }}</button>
          <button v-if="row.secret_configured" class="btn danger" :disabled="!!acting" @click="clearSecret(row)">移除</button>
        </div>
      </div>

      <details class="advanced-section service-advanced">
        <summary><span><strong>专业连接设置</strong><small>服务地址、模型和调用参数。</small></span><span>展开</span></summary>
        <div class="form-grid">
          <label>服务提供方
            <select class="input" v-model="row.provider" :disabled="user.role !== 'admin'"><option v-for="item in channelMeta[row.channel].providers" :key="item" :value="item">{{ displayLabel(providerLabels, item) }}</option></select>
          </label>
          <label>模型名称
            <input class="input" v-model.trim="row.model" :disabled="user.role !== 'admin' || row.channel === 'crossref' || row.provider === 'mock'" placeholder="模型 ID" />
          </label>
          <label class="span-2">服务地址
            <input class="input" type="url" v-model.trim="row.base_url" :disabled="user.role !== 'admin' || row.provider === 'mock'" placeholder="https://…" />
          </label>
          <label>等待时间（秒）<input class="input" type="number" min="1" max="300" v-model.number="row.timeout_sec" :disabled="user.role !== 'admin'" /></label>
          <label>同时处理数量<input class="input" type="number" min="1" max="32" v-model.number="row.max_concurrency" :disabled="user.role !== 'admin'" /></label>
        </div>

        <div v-if="row.channel === 'report_llm'" class="settings-panel">
          <h3>生成参数</h3><div class="form-grid">
            <label>最大输出长度<input class="input" type="number" min="1" max="10000" v-model.number="row.settings.max_tokens" :disabled="user.role !== 'admin'" /></label>
            <label>表达随机度<input class="input" type="number" min="0" max="2" step="0.1" v-model.number="row.settings.temperature" :disabled="user.role !== 'admin'" /></label>
            <label>最小调用间隔（秒）<input class="input" type="number" min="0" max="60" step="0.1" v-model.number="row.settings.min_interval_sec" :disabled="user.role !== 'admin'" /></label>
            <label v-if="['anthropic','claude'].includes(row.provider)">接口版本<input class="input" v-model.trim="row.settings.anthropic_version" :disabled="user.role !== 'admin'" /></label>
          </div>
        </div>
        <div v-else-if="row.channel === 'embedding'" class="settings-panel">
          <h3>语义检索参数</h3><div class="form-grid">
            <label>向量维度<input class="input" type="number" min="64" max="3072" v-model.number="row.settings.dimensions" :disabled="user.role !== 'admin'" /></label>
            <label>每批处理数量<input class="input" type="number" min="1" max="512" v-model.number="row.settings.batch_size" :disabled="user.role !== 'admin'" /></label>
            <label class="span-2">处理内容<select class="input" v-model="row.settings.input_scope" :disabled="user.role !== 'admin'"><option value="processed_chunks">已治理摘要</option><option value="fulltext_chunks">已治理全文（授权状态另行确认）</option></select></label>
          </div>
        </div>
        <div v-else-if="row.channel === 'evaluation'" class="settings-panel">
          <h3>质量评审参数</h3><div class="form-grid">
            <label>最大输出长度<input class="input" type="number" min="1" max="10000" v-model.number="row.settings.max_tokens" :disabled="user.role !== 'admin'" /></label>
            <label>表达随机度<input class="input" type="number" min="0" max="2" step="0.1" v-model.number="row.settings.temperature" :disabled="user.role !== 'admin'" /></label>
            <label>最小调用间隔（秒）<input class="input" type="number" min="0" max="60" step="0.1" v-model.number="row.settings.min_interval_sec" :disabled="user.role !== 'admin'" /></label>
            <label class="fixed-setting"><input type="checkbox" :checked="false" disabled /> 始终不发送全文</label>
          </div>
        </div>
        <button v-if="user.role === 'admin'" class="btn primary" :disabled="!!acting" @click="save(row)">{{ acting === `save:${row.channel}` ? "正在保存…" : "保存专业设置" }}</button>
      </details>

      <FeedbackBanner v-if="results[row.channel]" :kind="results[row.channel].ok ? 'success' : 'error'">
        <strong>{{ results[row.channel].ok ? "连接成功" : "连接失败" }}</strong>
        <span>{{ results[row.channel].latency_ms != null ? `${results[row.channel].latency_ms} ms` : "" }} {{ results[row.channel].message || results[row.channel].tested_with || "" }}</span>
        <details v-if="results[row.channel].error_code" class="inline-details"><summary>专业信息</summary><code>{{ results[row.channel].error_code }}</code></details>
      </FeedbackBanner>
    </section>
  </div>
</template>
