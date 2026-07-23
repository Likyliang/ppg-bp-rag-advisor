<script setup lang="ts">
import { onMounted, provide, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { api, jsonBody } from "./api";

type User = { id: string; username: string; role: string; auth_disabled?: boolean };

const route = useRoute();
const user = ref<User | null>(null);
const loading = ref(true);
const loginError = ref("");
const username = ref("");
const password = ref("");

const modules = [
  ["/", "概览"], ["/library", "文献工作台"], ["/knowledge", "知识库与索引"],
  ["/retrieval", "检索调试台"], ["/config", "配置中心"], ["/integrations", "外部 API 集成"],
  ["/quality", "质量评测"], ["/jobs", "任务中心"], ["/access", "访问与审计"],
];

provide("adminUser", user);

async function loadUser() {
  try { user.value = await api<User>("/api/v1/admin/auth/me"); }
  catch { user.value = null; }
  finally { loading.value = false; }
}

async function login() {
  loginError.value = "";
  try {
    const result = await api<{ user: User }>("/api/v1/admin/auth/login", {
      method: "POST", body: jsonBody({ username: username.value, password: password.value }),
    });
    user.value = result.user;
    password.value = "";
  } catch (error) { loginError.value = (error as Error).message; }
}

async function logout() {
  await api("/api/v1/admin/auth/logout", { method: "POST" });
  user.value = null;
}

onMounted(loadUser);
</script>

<template>
  <div v-if="loading" class="login-page"><div class="login-card">正在加载后台…</div></div>
  <div v-else-if="!user" class="login-page">
    <div class="login-card">
      <h1>高血压 RAG 治理后台</h1>
      <div class="muted">仅供内部知识治理与安全运维，不是医疗诊断系统。</div>
      <form @submit.prevent="login">
        <label>用户名<input class="input" v-model="username" autocomplete="username" /></label>
        <label>密码<input class="input" type="password" v-model="password" autocomplete="current-password" /></label>
        <div v-if="loginError" class="error">{{ loginError }}</div>
        <button class="btn primary" type="submit">登录</button>
      </form>
    </div>
  </div>
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand">RAG 治理后台<small>保守解释 · 证据可追溯</small></div>
      <nav class="nav">
        <RouterLink v-for="item in modules" :key="item[0]" :to="item[0]" :class="{ 'router-link-active': route.path === item[0] }">{{ item[1] }}</RouterLink>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="muted">内部协作版 · 不验证 PPG 血压估算准确性</div>
        <div class="user"><span>{{ user.username }} · {{ user.role }}</span><button class="btn" @click="logout">退出</button></div>
      </header>
      <RouterView />
    </main>
  </div>
</template>
