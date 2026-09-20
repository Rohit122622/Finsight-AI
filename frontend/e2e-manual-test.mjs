/**
 * FinSentry AI — Phase 5G Manual E2E Verification
 * Tests frontend routes and component availability via HTTP requests
 * This validates that the frontend serves expected content for all routes
 */

import http from "http";

const BASE_URL = "http://localhost:5173";

const routes = [
  { path: "/", name: "Root/Login", expectedContent: ["FinSentry", "login", "html"] },
  { path: "/login", name: "Login Page", expectedContent: ["html"] },
  { path: "/sessions", name: "Sessions Dashboard", expectedContent: ["html"] },
];

async function fetchPage(url) {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error("Timeout")), 10000);
    http.get(url, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        clearTimeout(timeout);
        resolve({ status: res.statusCode, body: data.toLowerCase() });
      });
    }).on("error", (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });
}

async function runTests() {
  console.log("======================================================================");
  console.log(" FinSentry AI — Phase 5G E2E Route Verification");
  console.log("======================================================================");
  console.log(`Base URL: ${BASE_URL}`);
  console.log("");

  let passed = 0;
  let failed = 0;
  const results = [];

  for (const route of routes) {
    const url = `${BASE_URL}${route.path}`;
    try {
      const { status, body } = await fetchPage(url);
      const hasContent = route.expectedContent.some((c) => body.includes(c.toLowerCase()));
      
      if (status === 200 && hasContent) {
        console.log(`✓ PASS: ${route.name} (${route.path}) - Status ${status}`);
        passed++;
        results.push({ route: route.name, status: "PASS", code: status });
      } else {
        console.log(`✗ FAIL: ${route.name} (${route.path}) - Status ${status}, Content check: ${hasContent}`);
        failed++;
        results.push({ route: route.name, status: "FAIL", code: status, reason: "Content mismatch" });
      }
    } catch (err) {
      console.log(`✗ FAIL: ${route.name} (${route.path}) - Error: ${err.message}`);
      failed++;
      results.push({ route: route.name, status: "FAIL", error: err.message });
    }
  }

  // Test Vite dev server health
  try {
    const { status } = await fetchPage(`${BASE_URL}/@vite/client`);
    if (status === 200) {
      console.log(`✓ PASS: Vite Dev Server - Status ${status}`);
      passed++;
    } else {
      console.log(`✗ FAIL: Vite Dev Server - Status ${status}`);
      failed++;
    }
  } catch (err) {
    console.log(`✗ FAIL: Vite Dev Server - ${err.message}`);
    failed++;
  }

  console.log("");
  console.log("----------------------------------------------------------------------");
  console.log(` RESULTS: ${passed} passed, ${failed} failed, ${passed + failed} total`);
  console.log("----------------------------------------------------------------------");
  
  process.exit(failed > 0 ? 1 : 0);
}

runTests().catch((err) => {
  console.error("Test runner error:", err);
  process.exit(1);
});
