import '@fontsource/ibm-plex-sans/latin-400.css';
import '@fontsource/ibm-plex-sans/latin-500.css';
import '@fontsource/ibm-plex-mono/latin-400.css';
import '@fontsource/ibm-plex-mono/latin-500.css';
import './styles/tokens.css';
import './styles/base.css';

import { mount } from 'svelte';
import App from './App.svelte';
import { start } from './lib/studio.svelte';

mount(App, { target: document.body });
void start();
