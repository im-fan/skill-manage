import { defineConfig } from "vite";

export default defineConfig({
  build: {
    outDir: "web/assets",
    lib: {
      entry: "src/web/main.ts",
      name: "SkillManageWorkbench",
      formats: ["es"],
      fileName: () => "skill-manage-support.js"
    },
    rollupOptions: {
      output: {
        entryFileNames: "skill-manage-support.js"
      }
    }
  }
});
