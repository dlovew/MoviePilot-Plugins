import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import _sfc_main from './__federation_expose_Config-DFpzD0I3.js';

true&&(function polyfill() {
  const relList = document.createElement("link").relList;
  if (relList && relList.supports && relList.supports("modulepreload")) {
    return;
  }
  for (const link of document.querySelectorAll('link[rel="modulepreload"]')) {
    processPreload(link);
  }
  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type !== "childList") {
        continue;
      }
      for (const node of mutation.addedNodes) {
        if (node.tagName === "LINK" && node.rel === "modulepreload")
          processPreload(node);
      }
    }
  }).observe(document, { childList: true, subtree: true });
  function getFetchOpts(link) {
    const fetchOpts = {};
    if (link.integrity) fetchOpts.integrity = link.integrity;
    if (link.referrerPolicy) fetchOpts.referrerPolicy = link.referrerPolicy;
    if (link.crossOrigin === "use-credentials")
      fetchOpts.credentials = "include";
    else if (link.crossOrigin === "anonymous") fetchOpts.credentials = "omit";
    else fetchOpts.credentials = "same-origin";
    return fetchOpts;
  }
  function processPreload(link) {
    if (link.ep)
      return;
    link.ep = true;
    const fetchOpts = getFetchOpts(link);
    fetch(link.href, fetchOpts);
  }
}());

const {createApp,h} = await importShared('vue');

// 仅用于 `npm run preview` 本地预览；宿主加载的是联邦暴露的 ./Config 远程组件。
const api = {
  get: async () => ({}),
  post: async () => ({}),
};

createApp({
  render: () => h(_sfc_main, {
    api,
    initialConfig: { name: '下载任务分类与标签魔改VUE版 -dlovew' },
    pluginId: 'DownloadSiteTagModdlovew',
  }),
}).mount('#app');
