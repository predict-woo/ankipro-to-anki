# Deployment Guide

## Netlify Deployment

This project is configured for easy deployment to Netlify. Follow these steps:

### Method 1: Git-based Deployment (Recommended)

1. **Push your code to a Git repository** (GitHub, GitLab, or Bitbucket)

2. **Connect to Netlify:**
   - Go to [netlify.com](https://netlify.com) and sign up/login
   - Click "New site from Git"
   - Choose your Git provider and repository
   - Configure build settings:
     - **Build command:** `npm run build`
     - **Publish directory:** `dist`
     - **Node version:** `18` (or latest LTS)

3. **Deploy:** Netlify will automatically build and deploy your site

### Method 2: Manual Deploy

1. **Build the project locally:**
   ```bash
   npm install
   npm run build
   ```

2. **Deploy the dist folder:**
   - Go to [netlify.com](https://netlify.com)
   - Drag and drop the `dist` folder to the deploy area

### Configuration Files

The project includes these configuration files for optimal Netlify deployment:

- **`netlify.toml`:** Build settings, redirects, and headers
- **`public/_headers`:** Additional headers for static assets
- **`vite.config.js`:** Optimized build configuration

### Features Configured

✅ **Single Page Application routing** - All routes redirect to index.html  
✅ **WASM file support** - Proper Content-Type headers for WebAssembly  
✅ **Security headers** - CSRF, XSS, and content security  
✅ **Caching optimization** - Long-term caching for static assets  
✅ **Code splitting** - Optimized chunks for faster loading  

### Environment Variables

No environment variables are required for this client-side application.

### Post-Deployment

After deployment, test the following:
- [ ] File upload functionality works
- [ ] OFC to APKG conversion completes successfully
- [ ] Generated APKG files download correctly
- [ ] No console errors related to WASM loading

### Troubleshooting

**WASM Loading Issues:**
- Ensure your domain serves WASM files with `Content-Type: application/wasm`
- Check that no ad blockers are interfering with WASM execution

**Build Failures:**
- Verify Node.js version is 18 or higher
- Run `npm install` to ensure all dependencies are installed
- Check that the build succeeds locally with `npm run build`

### Performance Notes

The app includes large dependencies (SQL.js, ZSTD WASM). The configuration:
- Splits vendor code into separate chunks
- Enables long-term caching for static assets
- Compresses assets with gzip

Expected load times:
- Initial load: 2-5 seconds (depending on connection)
- Subsequent loads: <1 second (cached assets) 