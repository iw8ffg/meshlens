import { mount } from 'svelte'
import '@fontsource/ibm-plex-sans/latin-400.css'
import '@fontsource/ibm-plex-sans/latin-500.css'
import '@fontsource/ibm-plex-sans/latin-600.css'
import '@fontsource/ibm-plex-mono/latin-400.css'
import '@fontsource/ibm-plex-mono/latin-500.css'
import './app.css'
import App from './App.svelte'
import { initTheme } from './lib/theme'
import { initLang } from './lib/i18n/index.svelte'
import { initViewport } from './lib/viewport.svelte'

// Tema e viewport vivono quanto la pagina: i listener non vanno rimossi prima.
initLang()
initTheme()
initViewport()

const app = mount(App, { target: document.getElementById('app')! })

export default app
