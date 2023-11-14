<template>
    <div id="app">
        <router-view></router-view>
    </div>
</template>

<script>
import Signup from './components/Signup.vue';
import Verify from './components/Verify.vue';
import Activity from './components/Activity.vue';
import ConfirmQueue from './components/ConfirmQueue.vue';

export default {
    name: "App",
    components: {
        Signup,
        Verify,
        Activity,
        ConfirmQueue
    },
};
</script>

<style>
</style>
