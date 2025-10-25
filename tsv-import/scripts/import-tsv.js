import { PrismaClient } from '@prisma/client';
import { parse } from 'csv-parse/sync';
import { promises as fs } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const prisma = new PrismaClient();

// Batch size for bulk operations
const BATCH_SIZE = 2000;

// Helper function to parse integer or return null
const parseIntOrNull = (value) => {
  if (!value || value.trim() === '') return null;
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? null : parsed;
};

// Transform TSV record to database record
function transformRecord(record) {
  const bookId = record['資料番号'];
  const indexInBook = record['資料内漢字番号'];
  const wordIndexInBook = record['資料内漢語番号'];

  if (!bookId || !indexInBook) {
    return null; // Skip invalid records
  }

  const characterId = `${bookId}_${indexInBook}`;
  const wordId = wordIndexInBook ? `${bookId}_${wordIndexInBook}` : characterId;

  return {
    character_id: characterId,
    book_id: bookId || null,
    book_name: record['資料名'] || null,
    index_in_book: parseIntOrNull(indexInBook),
    word_index_in_book: parseIntOrNull(wordIndexInBook),
    character: record['単字_見出し'] || null,
    character_original: record['単字_出現形'] || null,
    word_id: wordId,
    word: record['漢語_見出し'] || null,
    word_original: record['漢語_出現形'] || null,
    word_alphabet: record['漢語_alphabet'] || null,
    word_type: record['語種'] || null,
    pos_in_word: parseIntOrNull(record['漢語内位置']),
    len: record['単字長'] || null,
    shoten: record['声点'] || null,
    shoten_word: record['声点型'] || null,
    kana: record['仮名注'] || null,
    word_kana: record['仮名型'] || null,
    fanqie: record['反切'] || null,
    ruion: record['類音'] || null,
    hakase: record['節博士'] || null,
    etc: record['その他'] || null,
    position_in_book: record['出現位置'] || null,
    notes: record['備考'] || null
  };
}

// Process records in batches using raw SQL for better performance
async function insertBatchWithUpsert(batch) {
  const placeholders = [];
  const values = [];
  let paramIndex = 1;

  for (const record of batch) {
    const recordPlaceholders = [];
    for (let i = 0; i < 24; i++) {
      recordPlaceholders.push(`$${paramIndex++}`);
    }
    placeholders.push(`(${recordPlaceholders.join(', ')})`);

    values.push(
      record.character_id,
      record.book_id,
      record.book_name,
      record.index_in_book,
      record.word_index_in_book,
      record.character,
      record.character_original,
      record.word_id,
      record.word,
      record.word_original,
      record.word_alphabet,
      record.word_type,
      record.pos_in_word,
      record.len,
      record.shoten,
      record.shoten_word,
      record.kana,
      record.word_kana,
      record.fanqie,
      record.ruion,
      record.hakase,
      record.etc,
      record.position_in_book,
      record.notes
    );
  }

  const sql = `
    INSERT INTO "Dhsjr" (
      character_id, book_id, book_name, index_in_book, word_index_in_book,
      character, character_original, word_id, word, word_original,
      word_alphabet, word_type, pos_in_word, len, shoten,
      shoten_word, kana, word_kana, fanqie, ruion,
      hakase, etc, position_in_book, notes
    ) VALUES ${placeholders.join(', ')}
    ON CONFLICT (character_id) DO UPDATE SET
      book_id = EXCLUDED.book_id,
      book_name = EXCLUDED.book_name,
      index_in_book = EXCLUDED.index_in_book,
      word_index_in_book = EXCLUDED.word_index_in_book,
      character = EXCLUDED.character,
      character_original = EXCLUDED.character_original,
      word_id = EXCLUDED.word_id,
      word = EXCLUDED.word,
      word_original = EXCLUDED.word_original,
      word_alphabet = EXCLUDED.word_alphabet,
      word_type = EXCLUDED.word_type,
      pos_in_word = EXCLUDED.pos_in_word,
      len = EXCLUDED.len,
      shoten = EXCLUDED.shoten,
      shoten_word = EXCLUDED.shoten_word,
      kana = EXCLUDED.kana,
      word_kana = EXCLUDED.word_kana,
      fanqie = EXCLUDED.fanqie,
      ruion = EXCLUDED.ruion,
      hakase = EXCLUDED.hakase,
      etc = EXCLUDED.etc,
      position_in_book = EXCLUDED.position_in_book,
      notes = EXCLUDED.notes
  `;

  await prisma.$executeRawUnsafe(sql, ...values);
}

async function importTsvFile(filePath) {
  console.log(`Processing ${filePath}...`);
  const startTime = Date.now();

  const content = await fs.readFile(filePath, 'utf-8');

  // Parse TSV file
  const records = parse(content, {
    columns: true,
    delimiter: '\t',
    skip_empty_lines: true,
    relax_quotes: true,
    relax_column_count: true
  });

  console.log(`  Parsed ${records.length} records`);

  // Transform and filter records
  const transformedRecords = records
    .map(transformRecord)
    .filter(record => record !== null);

  const skippedCount = records.length - transformedRecords.length;
  console.log(`  Valid records: ${transformedRecords.length}, Skipped: ${skippedCount}`);

  // Process in batches
  let importedCount = 0;
  for (let i = 0; i < transformedRecords.length; i += BATCH_SIZE) {
    const batch = transformedRecords.slice(i, i + BATCH_SIZE);
    await insertBatchWithUpsert(batch);
    importedCount += batch.length;

    const progress = Math.min(100, ((i + batch.length) / transformedRecords.length * 100).toFixed(1));
    console.log(`  Progress: ${progress}% (${importedCount}/${transformedRecords.length})`);
  }

  const duration = ((Date.now() - startTime) / 1000).toFixed(2);
  const recordsPerSec = (importedCount / (duration || 1)).toFixed(0);
  console.log(`  Completed in ${duration}s (${recordsPerSec} records/sec)`);

  return { imported: importedCount, skipped: skippedCount };
}

async function main() {
  try {
    const startTime = Date.now();
    const dataDir = join(__dirname, '../..', 'data');
    const files = await fs.readdir(dataDir);
    const tsvFiles = files.filter(f => f.endsWith('.tsv'));

    console.log(`Found ${tsvFiles.length} TSV files to import\n`);

    let totalImported = 0;
    let totalSkipped = 0;

    for (const file of tsvFiles) {
      const filePath = join(dataDir, file);
      const { imported, skipped } = await importTsvFile(filePath);
      totalImported += imported;
      totalSkipped += skipped;
    }

    const totalDuration = ((Date.now() - startTime) / 1000).toFixed(2);
    const avgRecordsPerSec = (totalImported / (totalDuration || 1)).toFixed(0);

    console.log('\n=== Import Summary ===');
    console.log(`Total records imported: ${totalImported}`);
    console.log(`Total records skipped: ${totalSkipped}`);
    console.log(`Total time: ${totalDuration}s`);
    console.log(`Average speed: ${avgRecordsPerSec} records/sec`);
    console.log('Import completed successfully!');
  } catch (error) {
    console.error('Import failed:', error);
    process.exit(1);
  } finally {
    await prisma.$disconnect();
  }
}

main();
