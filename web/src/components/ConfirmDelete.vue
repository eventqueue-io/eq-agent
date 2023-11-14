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
      <h3 class="text-lg leading-6 font-medium text-gray-900" id="modal-headline">
        Confirm Deletion
      </h3>
      <div class="mt-2">
        <p class="text-sm text-gray-500">
          Are you sure you want to delete this endpoint? This action cannot be undone.
        </p>
      </div>
      <div class="flex justify-end space-x-4 mt-5">
        <button
            @click="$emit('cancel')"
            type="button"
            class="inline-flex justify-center rounded-md border border-gray-300 shadow-sm px-4 py-2 bg-white text-base font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
        >
          Cancel
        </button>
        <button
            @click="$emit('confirm-delete')"
            type="button"
            class="inline-flex justify-center rounded-md border border-transparent shadow-sm px-4 py-2 bg-red-600 text-base font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
        >
          Delete
        </button>
      </div>
    </div>
  </div>
</template>

<script>
export default {
  name: "ConfirmDelete",
};
</script>
