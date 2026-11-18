/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: { sans: ['"Segoe UI"', "Tahoma", '"Noto Naskh Arabic"', "Arial", "sans-serif"] },
      colors: { brand: { 50: "#eef5fa", 100: "#d5e6f1", 600: "#0f5e8c", 700: "#0d4f75", 800: "#0f3d5e" } },
    },
  },
  plugins: [],
};
