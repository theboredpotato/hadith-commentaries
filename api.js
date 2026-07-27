// api.js
const express = require('express');
const fs = require('fs/promises');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// This function scans all book folders inside data/fath_al_bari/
async function fetchCommentary(hadithNumber) {
  const bukhariRoot = path.join(__dirname, 'data', 'fath_al_bari');
  try {
    const bookDirs = await fs.readdir(bukhariRoot, { withFileTypes: true });
    for (const dirent of bookDirs) {
      if (!dirent.isDirectory()) continue;
      const bookDir = path.join(bukhariRoot, dirent.name);
      
      // Read all bab-*.json files in this book folder
      const files = await fs.readdir(bookDir);
      const babJsonFiles = files.filter(f => /^bab-\d+\.json$/i.test(f));
      
      for (const file of babJsonFiles) {
        const fullPath = path.join(bookDir, file);
        const raw = await fs.readFile(fullPath, 'utf-8');
        const data = JSON.parse(raw);
        
        // Check if this bab covers the requested hadith number
        if (Array.isArray(data.hadith_numbers) && data.hadith_numbers.includes(Number(hadithNumber))) {
          // Found it! Read the corresponding text file
          const commentaryPath = path.join(bookDir, data.commentary_file);
          const commentary = await fs.readFile(commentaryPath, 'utf-8');
          
          return {
            babNumber: data.bab_number,
            babTitle: data.bab_title,
            hadithNumbers: data.hadith_numbers,
            commentary
          };
        }
      }
    }
  } catch (err) {
    console.error('Error reading Bukhari directory:', err.message);
  }
  return null;
}

// Simple route to check if the API is online
app.get('/', (req, res) => {
  res.send('Fath al-Bari API is running!');
});

// The actual API route, e.g., /commentary/3
app.get('/commentary/:hadithNumber', async (req, res) => {
  try {
    const hadithNumber = parseInt(req.params.hadithNumber, 10);
    const commentary = await fetchCommentary(hadithNumber);
    
    if (!commentary) {
      return res.status(404).json({ error: 'Commentary not found for this hadith.' });
    }
    
    res.json(commentary);
  } catch (error) {
    console.error(error);
    res.status(500).json({ error: 'Internal server error.' });
  }
});

app.listen(PORT, () => {
  console.log(`API is live on port ${PORT}`);
});