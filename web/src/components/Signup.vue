<template>
  <div class="min-h-screen bg-gray-100 flex items-center justify-center">
    <div class="bg-white p-8 rounded shadow-md w-full max-w-md">
      <h2 class="text-2xl font-semibold mb-6">Sign up</h2>
      <form @submit.prevent="submit" class="w-full max-w-lg">
        <label for="email" class="block mb-2">Enter your email address</label>
        <input
            id="email"
            v-model="email"
            type="email"
            maxlength="255"
            class="block w-full mb-4 p-2 border border-gray-300 rounded"
        />
        <button
            type="submit"
            :disabled="loading"
            :class="loading ? 'w-full p-2 bg-gray-500 text-white rounded' : 'w-full p-2 bg-green-500 text-white rounded'"
        >
          {{ loading ? "Waiting for response..." : "Submit" }}
        </button>
        <router-link
            to="/verify"
            class="w-full mt-4 p-2 bg-blue-500 text-white rounded block text-center"
        >
          I have already signed up, skip this
        </router-link>
        <div v-if="error" class="mt-4 text-red-500">{{ error }}</div>
      </form>
    </div>
  </div>
</template>

<script lang="ts">
import {defineComponent, onMounted, ref} from 'vue';
import {useRouter} from 'vue-router';

export default defineComponent({
  name: 'Signup',
  setup() {
    const email = ref('');
    const error = ref(null);
    const loading = ref(false);
    const router = useRouter();

    onMounted(async () => {
      try {
        const response = await fetch(`/api/users/me`, {
          method: 'GET',
        });

        const data = await response.json();
        if (response.status == 200) {
          if (data.verified) {
            await router.push('/activity');
          }
        } else {
          error.value = data.message || 'An error occurred';
        }
      } catch (err) {
        console.log(err);
        error.value = 'An error occurred: ' + err;
      }
    });

    const submit = async () => {
      loading.value = true;
      error.value = null;

      try {
        const response = await fetch('/api/users/', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({email: email.value}),
        });

        if (response.status === 200 || response.status === 201) {
          await router.push('/verify');
        } else if (response.status === 409) {
          error.value = 'User already exists';
        } else if (response.status === 403) {
          const body = await response.json();
          console.log(body)
          if (body.detail.message === "New users are not allowed") {
            if (body.detail.ref != null && body.detail.ref !== "")
              await router.push('/notify-me?ref=' + body.detail.ref);
            else
              await router.push('/notify-me');
          }
        } else {
          const data = await response.json();
          error.value = data.message || 'An error occurred';
        }
      } catch (err) {
        error.value = 'An error occurred: ' + err;
      } finally {
        loading.value = false;
      }
    };

    return {
      email,
      error,
      submit,
      loading
    };
  },
});
</script>
