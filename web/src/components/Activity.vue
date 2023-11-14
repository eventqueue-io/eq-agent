<template>
  <div class="min-h-screen bg-gray-100">
    <div class="container mx-auto px-4 py-10">
      <h2 class="text-3xl font-semibold mb-6">Activity</h2>
      <div class="grid grid-cols-1 gap-6">
        <div class="bg-white p-6 rounded shadow-md">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-semibold">Endpoints</h3>
            <button @click="showModal = true" class="bg-green-500 text-white font-semibold py-2 px-4 rounded">
              +
            </button>
          </div>
          <table class="w-full text-left border-collapse">
            <thead>
            <tr>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Local URL</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Description</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Created</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Last Used</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Actions</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="endpoint in endpoints" :key="endpoint.id" class="text-sm leading-relaxed">
              <td class="border-b border-gray-300 p-2">{{ endpoint.private_url }}</td>
              <td class="border-b border-gray-300 p-2">{{ endpoint.description }}</td>
              <td class="border-b border-gray-300 p-2">{{ formatDate(endpoint.created) }}</td>
              <td class="border-b border-gray-300 p-2">{{
                  endpoint.last_used ? formatDate(endpoint.last_used) : ""
                }}
              </td>
              <td class="border-b border-gray-300 p-2 flex">
                <button
                    title="Copy endpoint's remote URL to clipboard"
                    @click="copyToClipboard(endpoint.id)"
                    class="text-blue-500 hover:text-blue-700 mx-2"
                >
                  <font-awesome-icon
                      :icon="copiedEndpoints[endpoint.id] ? 'check' : 'copy'"
                      :class="copiedEndpoints[endpoint.id] ? 'text-green-500 hover:text-green-700' : 'text-blue-500 hover:text-blue-700'"
                      alt="Copy endpoint's remote URL"
                  />
                </button>
                <button title="Delete endpoint" @click="confirmDelete(endpoint.id)"
                        class="text-red-500 hover:text-red-700">
                  <font-awesome-icon icon="trash" class="text-red-500 hover:text-red-700" alt="Delete endpoint"/>
                </button>
              </td>
            </tr>
            </tbody>
          </table>
          <div v-show="copied" class="text-green-500 mt-4 transition duration-1000" :class="{ 'opacity-0': fading }">
            Copied!
          </div>
        </div>
        <!-- Pending section -->
        <div class="bg-white p-6 rounded shadow-md">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-semibold">Pending</h3>
          </div>
          <table class="w-full text-left border-collapse">
            <thead>
            <tr>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">ID</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">URL</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Created</th>
              <th class="border-b-2 border-gray-300 text-gray-600 font-medium">Actions</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="item in pending" :key="item.id" class="text-sm leading-relaxed">
              <td class="border-b border-gray-300 p-2">{{ item.id }}</td>
              <td class="border-b border-gray-300 p-2">{{ item.private_url }}</td>
              <td class="border-b border-gray-300 p-2">{{ formatDate(item.created) }}</td>
              <td class="border-b border-gray-300 p-2 flex">
                <button
                    title="Delete item"
                    @click="confirmDeleteItem(item.id)"
                    v-if="item.encrypted"
                    class="text-red-500 hover:text-red-700"
                >
                  <font-awesome-icon icon="trash" alt="Delete item"/>
                </button>
                <div v-else>
                  <button
                      title="Retry delivery"
                      @click="retryDelivery(item.id)"
                      class="text-blue-500 hover:text-blue-700 mr-2"
                  >
                    <font-awesome-icon icon="redo" alt="Reload item"/>
                  </button>
                  <button
                      title="Delete item"
                      @click="confirmDeleteItem(item.id)"
                      class="text-red-500 hover:text-red-700"
                  >
                    <font-awesome-icon icon="trash" alt="Delete item"/>
                  </button>
                </div>
              </td>
            </tr>
            </tbody>
          </table>
        </div>

        <!-- Log section -->
        <div class="bg-white p-6 rounded shadow-md">
          <h3 class="text-xl font-semibold mb-4">Live Webhook Forwarding Log</h3>
          <div class="h-64 overflow-y-auto">
            <div v-for="log in messageLog" :key="log.call_id" class="border-b border-gray-300 p-2">
              {{ log }}
            </div>
          </div>
        </div>
      </div>
    </div>
    <add-endpoint-modal v-if="showModal" @close="showModal = false" @endpointAdded="fetchEndpoints"/>
    <confirm-delete
        v-if="showDeleteModal"
        @confirmDelete="deleteEndpoint"
        @cancel="showDeleteModal = false"
    />
    <confirm-delete
        v-if="showDeleteItemModal"
        @confirmDelete="deleteItem"
        @cancel="showDeleteItemModal = false"
    />
  </div>
</template>


<script>
import {ref, onMounted, onUnmounted, watch, nextTick} from 'vue';
import AddEndpointModal from './AddEndpointModal.vue';
import ConfirmDelete from './ConfirmDelete.vue';

export default {
  components: {
    AddEndpointModal,
    ConfirmDelete
  },
  methods: {
    formatDate(dateString) {
      const options = {year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit'};
      const date = new Date(dateString);
      return date.toLocaleDateString('en-US', options);
    },
    async copyToClipboard(id) {
      try {
        await navigator.clipboard.writeText("https://app.eventqueue.io/hooks/" + id);
        this.copiedEndpoints[id] = true;

        setTimeout(() => {
          this.copiedEndpoints[id] = false;
        }, 3000);
      } catch (err) {
        console.error('Failed to copy text: ', err);
      }
    },
    confirmDelete(id) {
      this.deleteEndpointId = id;
      this.showDeleteModal = true;
    },
    async deleteEndpoint() {
      try {
        const response = await fetch(`/api/endpoints/${this.deleteEndpointId}`, {
          method: 'DELETE',
        });

        if (response.status === 200) {
          // Refresh the table
          this.fetchEndpoints();
        } else {
          const data = await response.json();
          this.error.value = data.message || 'An error occurred while deleting the endpoint';
        }
      } catch (err) {
        this.error.value = 'An error occurred while deleting the endpoint';
      }

      // Close the delete modal after attempting the deletion
      this.showDeleteModal = false;
    },
    confirmDeleteItem(id) {
      this.deleteItemId = id;
      this.showDeleteItemModal = true;
    },
    async deleteItem() {
      try {
        const response = await fetch(`/api/calls/${this.deleteItemId}`, {
          method: 'DELETE',
        });

        if (response.status === 200) {
          this.fetchPending();
        } else {
          const data = await response.json();
          this.error.value = data.message || 'An error occurred while deleting the item';
        }
      } catch (err) {
        this.error.value = 'An error occurred while deleting the item';
      }

      this.showDeleteItemModal = false;
    },
    async retryDelivery(id) {
      try {
        const response = await fetch(`/api/calls/${id}/retry`, {
          method: 'POST',
        });

        if (response.status === 200) {
          this.fetchPending();
        } else {
          const data = await response.json();
          this.error.value = data.message || 'An error occurred while reloading the item';
        }
      } catch (err) {
        this.error.value = 'An error occurred while reloading the item';
      }
    },
  },
  data() {
    return {
      copiedEndpoints: {},
      showDeleteModal: false,
      deleteEndpointId: null,
      showDeleteItemModal: false,
      deleteItemId: null,
    };
  },
  setup() {
    const messageLog = ref([]);
    const socket = ref(null);
    const error = ref('');
    const endpoints = ref([]);
    const pending = ref([]);

    const showModal = ref(false);
    const copied = ref(false);
    const fading = ref(false);

    async function fetchEndpoints() {
      try {
        const response = await fetch(`/api/endpoints/`, {
          method: 'GET',
        });

        if (response.status === 200) {
          const data = await response.json();
          endpoints.value = data;
        } else {
          const data = await response.json();
          error.value = data.message || 'An error occurred';
        }
      } catch (err) {
        error.value = 'An error occurred';
      }
    }

    async function fetchPending() {
      try {
        const response = await fetch(`/api/calls/`, {
          method: 'GET',
        });

        if (response.status === 200) {
          const data = await response.json();
          pending.value = data;
        } else {
          const data = await response.json();
          error.value = data.message || 'An error occurred';
        }
      } catch (err) {
        error.value = 'An error occurred';
      }
    }

    function sseConnect() {
      if (socket.value) {
        socket.value.close();
      }

      const protocol = window.location.protocol;
      const authority = window.location.host;
      socket.value = new EventSource(`${protocol}//${authority}/api/events`);

      socket.value.onmessage = (event) => {
        const data = JSON.parse(event.data);
        messageLog.value.push(data.message);
        fetchPending();
      };

      socket.value.onerror = (error) => {
        console.error('SSE error:', error);
        // Retry connection in 5 seconds
        setTimeout(sseConnect, 5000);
      };
    }

    onMounted(async () => {
      error.value = '';

      await fetchEndpoints();
      await fetchPending();
      sseConnect();
    });

    onUnmounted(() => {
      // Close the WebSocket connection when the component is unmounted
      if (socket.value) {
        socket.value.close();
      }
    });

    return {
      endpoints,
      pending,
      messageLog,
      showModal,
      copied,
      fading,
      fetchEndpoints,
      fetchPending
    };
  },
};
</script>


<style scoped>

</style>
