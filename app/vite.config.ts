import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Base relative pour un déploiement sur GitHub Pages
// (https://vernetmarc-glitch.github.io/carte-univers-observable/)
export default defineConfig({
  plugins: [react()],
  base: './',
})
