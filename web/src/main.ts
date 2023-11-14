import { createApp } from 'vue';
import './tailwind.css';
import { library } from '@fortawesome/fontawesome-svg-core';
import { faTrash, faCopy, faCheck, faRedo } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome';
import App from './App.vue';
import router from './router';

library.add(faTrash, faCopy, faCheck, faRedo);

const app = createApp(App).use(router);

app.component('font-awesome-icon', FontAwesomeIcon);
app.mount('#app');
