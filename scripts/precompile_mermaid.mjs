// Release-time SVG compilation; ordinary report generation uses verified SVGs.
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
const [toolRoot, jobFile, chromium, fontCSS] = process.argv.slice(2);
const requireTool = createRequire(path.resolve(toolRoot, 'package.json'));
const {renderMermaid} = await import(pathToFileURL(requireTool.resolve('@mermaid-js/mermaid-cli')).href);
const puppeteerModule = await import(pathToFileURL(requireTool.resolve('puppeteer')).href);
const puppeteer = puppeteerModule.default;
const jobs = JSON.parse(await fs.readFile(jobFile, 'utf8'));
const browser = await puppeteer.launch({executablePath:chromium==='auto'?undefined:chromium, headless:true, args:['--no-sandbox']});
try {
  for (const job of jobs) {
    const {data} = await renderMermaid(browser, job.source, 'svg', {
      svgId:'br-'+job.digest.slice(0,16),
      backgroundColor:'transparent', fontEmbed:false,
      mermaidConfig:{theme:'base',fontFamily:'BioReport-Latin, BioReport-CN, sans-serif',
        themeVariables:{primaryColor:'#eff6ff',primaryTextColor:'#203a5f',lineColor:'#52657d',fontSize:'15px'}},
      customFontCSS:[{cssUrl:pathToFileURL(path.resolve(fontCSS)),allowParentDirectoryLevel:0}]
    });
    await fs.writeFile(job.output, data);
    process.stdout.write(job.digest+' '+job.output+'\n');
  }
} finally {await browser.close();}
