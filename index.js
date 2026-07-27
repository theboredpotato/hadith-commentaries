const express = require('express');
const fs = require('fs/promises');
const path = require('path');

const app = express();

app.get('/api/commentary/:hadithNumber', async (req, res) => {
  try {
    const hadithNumber = req.params.hadithNumber;
    const targetNumber = Number(hadithNumber);
    
    const bukhariRoot = path.join(__dirname, 'data', 'fath_al_bari');
    const bookDirs = await fs.readdir(bukhariRoot, { withFileTypes: true });
    
    for (const dirent of bookDirs) {
      if (!dirent.isDirectory()) continue;
      
      const bookDir = path.join(bukhariRoot, dirent.name);
      const files = await fs.readdir(bookDir);
      const babJsonFiles = files.filter(f => /^bab-\d+\.json$/i.test(f));
      
      for (const file of babJsonFiles) {
        const fullPath = path.join(bookDir, file);
        const raw = await fs.readFile(fullPath, 'utf-8');
        const data = JSON.parse(raw);
        
        const numbersInBab = (data.hadith_numbers || []).map(Number);
        
        if (numbersInBab.includes(targetNumber)) {
          const commentaryPath = path.join(bookDir, data.commentary_file);
          const commentary = await fs.readFile(commentaryPath, 'utf-8');
          
          return res.status(200).json({
            babNumber: data.bab_number,
            babTitle: data.bab_title,
            hadithNumbers: numbersInBab,
            commentary
          });
        }
      }
    }
    
    return res.status(404).json({ error: 'Commentary not found for this hadith.' });
  } catch (error) {
    console.error('Error:', error.message);
    return res.status(500).json({ error: 'Internal server error.', details: error.message });
  }
});

module.exports = app;