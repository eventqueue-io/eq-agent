<template>
  <div
      class="
      fixed
      inset-0
      flex
      items-center
      justify-center
      bg-black
      bg-opacity-50
      z-50
    "
  >
    <div class="bg-white p-8 rounded shadow-lg w-full max-w-md">
      <h2 class="text-xl font-semibold mb-4">Add New Endpoint</h2>
      <form @submit.prevent="submitForm">
        <div class="mb-4">
          <label for="privateUrl" class="block text-sm font-medium mb-2">Private URL</label>
          <input
              id="privateUrl"
              v-model="privateUrl"
              type="text"
              class="w-full border border-gray-300 rounded py-2 px-4 text-sm"
              required
          />
        </div>
        <div class="mb-4">
          <label for="description" class="block text-sm font-medium mb-2">Description</label>
          <input
              id="description"
              v-model="description"
              type="text"
              class="w-full border border-gray-300 rounded py-2 px-4 text-sm"
          />
        </div>
        <div v-if="errorMessage" class="text-red-500">{{ errorMessage }}</div>
        <div class="flex justify-end space-x-4">
          <button
              @click="$emit('close')"
              type="button"
              class="mt-3 inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 sm:mt-0 sm:w-auto sm:text-sm"
          >
            Cancel
          </button>
          <button
              type="submit"
              class="mt-3 inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-green-500 text-base font-medium text-white hover:bg-green-600 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 sm:mt-0 sm:w-auto sm:text-sm"
          >
            Add Endpoint
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<script>
export default {
  name: 'AddEndpointModal',
  data() {
    return {
      privateUrl: '',
      description: '',
      errorMessage: null
    };
  },
  methods: {
    async submitForm() {
      this.errorMessage = null;
      try {
        const response = await fetch('/api/endpoints/', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            private_url: this.privateUrl,
            description: this.description,
          }),
        });

        if (response.status === 201) {
          this.$emit('endpoint-added');
          this.$emit('close');
          await fetchEndpoints();
        } else {
          // Handle other error responses here
          this.errorMessage = `Error adding endpoint: ${response.status}`;
        }
      } catch (error) {
        this.errorMessage = `Error adding endpoint: ${error.message}`;
      }
    },
  },
};
</script>
