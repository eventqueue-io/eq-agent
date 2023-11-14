import { createRouter, createWebHistory, RouteRecordRaw } from 'vue-router';
import Signup from '../components/Signup.vue';
import Verify from '../components/Verify.vue';
import Activity from '../components/Activity.vue';
import ConfirmQueue from "../components/ConfirmQueue.vue";

const routes: RouteRecordRaw[] = [
    { path: '/', component: Signup },
    { path: '/verify', component: Verify },
    { path: '/activity', component: Activity },
    { path: '/notify-me', component: ConfirmQueue },
];

const router = createRouter({
    history: createWebHistory(),
    routes,
});

export default router;
