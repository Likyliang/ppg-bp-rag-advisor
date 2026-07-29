<script setup lang="ts">
import { onMounted, onUnmounted, provide, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { api, jsonBody } from "./api";

type User = { id: string; username: string; role: string; auth_disabled?: boolean };

const route = useRoute();
const user = ref<User | null>(null);
const loading = ref(true);
const loginBusy = ref(false);
const loginError = ref("");
const username = ref("");
const password = ref("");

const modules = [
  ["/", "概览", "览"], ["/library", "文献工作台", "文"], ["/knowledge", "知识库与索引", "库"],
  ["/retrieval", "检索调试台", "检"], ["/config", "配置中心", "配"], ["/integrations", "外部 API 集成", "接"],
  ["/quality", "质量评测", "质"], ["/jobs", "任务中心", "任"], ["/access", "访问与审计", "审"],
];

provide("adminUser", user);

async function loadUser() {
  try { user.value = await api<User>("/api/v1/admin/auth/me"); }
  catch { user.value = null; }
  finally { loading.value = false; }
}

async function login() {
  loginError.value = "";
  loginBusy.value = true;
  try {
    const result = await api<{ user: User }>("/api/v1/admin/auth/login", {
      method: "POST", body: jsonBody({ username: username.value, password: password.value }),
    });
    user.value = result.user;
    password.value = "";
  } catch (error) { loginError.value = (error as Error).message; }
  finally { loginBusy.value = false; }
}

async function logout() {
  try { await api("/api/v1/admin/auth/logout", { method: "POST" }); }
  finally { user.value = null; }
}

function expireSession() {
  user.value = null;
  loginError.value = "登录已失效，请重新登录";
}

onMounted(() => {
  window.addEventListener("admin:unauthorized", expireSession);
  void loadUser();
});
onUnmounted(() => window.removeEventListener("admin:unauthorized", expireSession));
</script>

<template>
  <div v-if="loading" class="login-page"><div class="login-card">正在加载后台…</div></div>
  <div v-else-if="!user" class="login-page">
    <div class="login-card">
      <div class="login-mark">RAG</div>
      <h1>高血压 RAG 治理后台</h1>
      <div class="muted">仅供内部知识治理与安全运维，不是医疗诊断系统。</div>
      <form @submit.prevent="login">
        <label>用户名<input class="input" v-model.trim="username" autocomplete="username" required autofocus /></label>
        <label>密码<input class="input" type="password" v-model="password" autocomplete="current-password" required /></label>
        <div v-if="loginError" class="error">{{ loginError }}</div>
        <button class="btn primary" type="submit" :disabled="loginBusy">{{ loginBusy ? "正在登录…" : "登录" }}</button>
      </form>
    </div>
  </div>
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand">RAG 治理后台<small>保守解释 · 证据可追溯</small></div>
      <nav class="nav">
        <RouterLink v-for="item in modules" :key="item[0]" :to="item[0]" :class="{ 'router-link-active': route.path === item[0] }">
          <span class="nav-icon">{{ item[2] }}</span><span>{{ item[1] }}</span>
        </RouterLink>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="topbar-note"><span class="system-dot"></span>内部协作版 · 不验证 PPG 血压估算准确性</div>
        <div class="user"><span class="user-chip">{{ user.username }} · {{ user.role }}</span><button class="btn ghost" @click="logout">退出</button></div>
      </header>
      <RouterView />
    </main>
  </div>
</template>
