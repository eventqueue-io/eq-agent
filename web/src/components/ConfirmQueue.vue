<template>
  <div class="min-h-screen bg-gray-100 flex items-center justify-center">
    <div class="bg-white p-8 rounded shadow-md w-full max-w-md">
      <div v-if="showForm">
        <h2 class="text-2xl font-semibold mb-6">Verify</h2>
        <p class="mb-6">The maximum number of user accounts while in beta has been reached. If you want us to notify you when we increase that limit, click the button below.</p>
        <form @submit.prevent="submitForm">
          <input
              hidden="hidden"
              type="text"
              id="queue_ref"
              v-model="queue_ref"
              required
          />
          <div v-if="error" class="text-red-500 mb-4">{{ error }}</div>
          <button type="submit" class="w-full bg-green-500 text-white font-semibold py-2 rounded">Submit</button>
        </form>
      </div>
      <div v-else>
        <h2 class="text-2xl font-semibold mb-6">Alright!</h2>
        <p class="mb-6">We've made a note, and will reach out via email as soon as we open more accounts to beta testers.</p>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
import {defineComponent, onMounted, ref} from 'vue';
import {useRouter} from 'vue-router';

export default defineComponent({
  name: 'ConfirmQueue',
  setup() {
    const router = useRouter();
    const queue_ref = ref('');
    const error = ref('');
    const showForm = ref(true);

    const submitForm = async () => {
      error.value = '';

      try {
        const response = await fetch(`/api/users/queue/${encodeURIComponent(queue_ref.value)}`);
        if (!response.ok) {
          const data = await response.json();
          throw new Error(data.message || 'Confirmation failed');
        } else
          showForm.value = false;
      } catch (err) {
        error.value = 'An error occurred: ' + err.message;
      }
    };

    onMounted(async () => {
      try {
        const urlParams = new URLSearchParams(window.location.search);
        queue_ref.value = urlParams.get('ref');
      } catch (err) {
        error.value = 'An error occurred: ' + err.message;
      }
    });

    return {
      queue_ref,
      error,
      submitForm,
      showForm
    };
  },
});
</script>

<style scoped>
/* Add any component-specific styles here */
</style>
