<template>
  <div class="min-h-screen bg-gray-100 flex items-center justify-center">
    <div class="bg-white p-8 rounded shadow-md w-full max-w-md">
      <h2 class="text-2xl font-semibold mb-6">Verify</h2>
      <p class="mb-6">Please check your email for the verification token and enter it below:</p>
      <form @submit.prevent="submitForm">
        <label for="token" class="block font-medium mb-2">Verification Token</label>
        <input
            type="text"
            id="token"
            v-model="token"
            class="w-full border border-gray-300 rounded px-3 py-2 mb-4"
            required
        />
        <div v-if="error" class="text-red-500 mb-4">{{ error }}</div>
        <button type="submit" class="w-full bg-green-500 text-white font-semibold py-2 rounded">Submit</button>
      </form>
    </div>
  </div>
</template>

<script lang="ts">
import {defineComponent, onMounted, ref} from 'vue';
import {useRouter} from 'vue-router';

export default defineComponent({
  name: 'Verify',
  setup() {
    const router = useRouter();
    const token = ref('');
    const error = ref('');

    const submitForm = async () => {
      error.value = '';

      try {
        const verifyResponse = await fetch(`/api/users/verify/${encodeURIComponent(token.value)}`);
        if (!verifyResponse.ok) {
          const data = await verifyResponse.json();
          throw new Error(data.message || 'Verification failed');
        }

        const keyResponse = await fetch(`/api/users/key`, { method: 'POST' });
        if (!keyResponse.ok) {
          const data = await keyResponse.json();
          throw new Error(data.message || 'Key retrieval failed');
        }

        await router.push('/activity');
      } catch (err) {
        error.value = 'An error occurred: ' + err.message;
      }
    };

    onMounted(async () => {
      try {
        const response = await fetch(`/api/users/me`);
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.message || 'User check failed');
        }

        const data = await response.json();
        if (data.verified) {
          await router.push('/activity');
        }
      } catch (err) {
        error.value = 'An error occurred: ' + err.message;
      }
    });

    return {
      token,
      error,
      submitForm,
    };
  },
});
</script>

<style scoped>
/* Add any component-specific styles here */
</style>
