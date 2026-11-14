-- scanstudio.lua: le trascrizioni di Scan Studio in nvim, da leggere e da cui prendere.
-- I file li scrive Scan Studio (Outputs › Transcriptions for nvim, formato Markdown) e sono in sola
-- lettura: qui si legge, si copia una parte, la si mette in una nota con il suo indirizzo. Le
-- correzioni si fanno nello studio, che riscrive la cartella.
--
--   require('scanstudio').setup({ dir = '~/wiki/scans' })
--
--   :Scans         sceglie una fonte (Telescope se c'e', altrimenti vim.ui.select) e la apre
--   :ScansGrep     cerca nel testo di tutte le fonti
--   :ScanTake      copia il testo sotto il cursore (il taglio, o la sua zona "## ") negli appunti
--   :ScanInsert    sceglie una parte fra tutte le fonti e la mette nella nota qui, col suo indirizzo
--
-- Tasti (con setup({ keys = true }), il default): <leader>yo  <leader>yg  <leader>yt  <leader>yi

local M = { dir = vim.fn.expand('~/Documents/Scan Studio transcriptions') }

local function files()
  -- Markdown o LaTeX, come li scrive lo studio (journal.tex raccoglie solo, non e' una trascrizione)
  local out = vim.fn.globpath(M.dir, '*.md', false, true)
  for _, f in ipairs(vim.fn.globpath(M.dir, '*.tex', false, true)) do
    if vim.fn.fnamemodify(f, ':t') ~= 'journal.tex' then out[#out + 1] = f end
  end
  return out
end

local function read(path)
  local ok, lines = pcall(vim.fn.readfile, path)
  return ok and lines or {}
end

local function from_tex(lines)
  -- un file LaTeX dello studio, letto come se fosse Markdown: front matter dai commenti e dal titolo, il testo
  -- senza comandi (le righe restano righe, \subsection* diventa "## ")
  local t, body, inside = {}, {}, false
  for _, l in ipairs(lines) do
    local part = l:match('^%% (scanstudio://region/[%w%-]+)')
    if part then t.part = part; t.source = l:match('source (scanstudio://item/[%w%-]+)') end
    if l:match('^\\begin{document}') then inside = true
    elseif l:match('^\\end{document}') then inside = false
    elseif inside then
      local title = l:match('^\\section%*{(.*)}$')
      local sub = l:match('^\\emph{(.*)}$')
      local area = l:match('^\\subsection%*{(.*)}$')
      if title then t.title = title
      elseif sub and not t.date then t.date = sub:match('^(%d%d%d%d%-%d%d%-%d%d)') or ''
      elseif area then body[#body + 1] = '## ' .. area
      elseif not l:match('^\\begin{') and not l:match('^\\end{') and not l:match('includegraphics') then
        l = l:gsub('^\\item ', '- '):gsub('\\\\$', ''):gsub('\\textbf{(.-)}', '**%1**'):gsub('\\emph{(.-)}', '*%1*')
        l = l:gsub('\\textbackslash{}', '\\'):gsub('\\textasciitilde{}', '~'):gsub('\\%^{}', '^'):gsub('\\([&%%$#_{}])', '%1')
        body[#body + 1] = l
      end
    end
  end
  for _, k in ipairs({ 'title', 'date' }) do if t[k] then t[k] = t[k]:gsub('\\([&%%$#_{}])', '%1') end end
  local out = { '---', '---' }
  vim.list_extend(out, body)
  return t, out
end

local function front(lines)
  -- il front matter: title, date, id, source
  local t = {}
  if lines[1] ~= '---' then return t end
  for i = 2, #lines do
    if lines[i] == '---' then break end
    local k, v = lines[i]:match('^(%w+):%s*(.-)%s*$')
    if k then t[k] = v:gsub('^"(.*)"$', '%1'):gsub('\\"', '"') end
  end
  return t
end

local function parts(path)
  -- il testo di un taglio e le sue zone: { name, region, text } (senza il commento con l'indirizzo)
  local lines, out, cur = read(path), {}, nil
  local f, body
  if path:match('%.tex$') then f, lines = from_tex(lines) else f = front(lines) end
  body = 1
  if lines[1] == '---' then
    for i = 2, #lines do if lines[i] == '---' then body = i + 1 break end end
  end
  local whole = {}
  for i = body, #lines do
    local l = lines[i]
    local h = l:match('^## (.*)')
    if h then
      cur = { name = h, text = {}, source = f.source, title = f.title, date = f.date }
      out[#out + 1] = cur
    elseif cur then
      local r = l:match('^<!%-%- (scanstudio://region/[%w%-]+)')
      if r then cur.region = r else cur.text[#cur.text + 1] = l end
    else
      whole[#whole + 1] = l
    end
  end
  if vim.trim(table.concat(whole, '\n')) ~= '' then
    table.insert(out, 1, { name = '', text = whole, source = f.source, title = f.title, date = f.date, region = f.part })
  end
  for _, p in ipairs(out) do p.text = vim.trim(table.concat(p.text, '\n')) end
  return out, f
end

local function cite(p)
  -- da dove viene: invisibile nella stampa (commento HTML, o % in una nota LaTeX), cliccabile da Scan Studio
  local what = (p.title or '') .. (p.name ~= '' and (' · ' .. p.name) or '')
  local line = ('from Scan Studio: %s%s, %s'):format(what, p.date and p.date ~= '' and (', ' .. p.date) or '', p.region or p.source or '')
  if vim.bo.filetype == 'tex' or vim.bo.filetype == 'plaintex' then return '% ' .. line end
  return '<!-- ' .. line .. ' -->'
end

local function open(path)
  vim.cmd.edit(vim.fn.fnameescape(path))
end

function M.pick()
  local items = {}
  for _, path in ipairs(files()) do
    local f = path:match('%.tex$') and (from_tex(read(path))) or front(read(path))
    items[#items + 1] = { path = path, label = ((f.date or '') .. '  ' .. (f.title or vim.fn.fnamemodify(path, ':t:r'))) }
  end
  table.sort(items, function(a, b) return a.label > b.label end)    -- le piu' recenti in cima
  local ok = pcall(require, 'telescope.pickers')
  if ok then
    local pickers, finders, conf = require('telescope.pickers'), require('telescope.finders'), require('telescope.config').values
    local actions, state = require('telescope.actions'), require('telescope.actions.state')
    pickers.new({}, {
      prompt_title = 'Scan Studio',
      finder = finders.new_table({ results = items, entry_maker = function(e) return { value = e, display = e.label, ordinal = e.label, path = e.path } end }),
      sorter = conf.generic_sorter({}), previewer = conf.file_previewer({}),
      attach_mappings = function(buf)
        actions.select_default:replace(function() actions.close(buf); open(state.get_selected_entry().path) end)
        return true
      end,
    }):find()
  else
    vim.ui.select(items, { prompt = 'Scan Studio', format_item = function(e) return e.label end }, function(e) if e then open(e.path) end end)
  end
end

function M.grep()
  local ok, tb = pcall(require, 'telescope.builtin')
  if ok then return tb.live_grep({ cwd = M.dir, prompt_title = 'Scan Studio text', glob_pattern = '*.md' }) end
  vim.ui.input({ prompt = 'Search the transcriptions: ' }, function(q)
    if q and q ~= '' then vim.cmd('vimgrep /' .. vim.fn.escape(q, '/') .. '/j ' .. vim.fn.fnameescape(M.dir) .. '/*.md | copen') end
  end)
end

function M.take()
  -- la parte sotto il cursore, intera, negli appunti (con la riga da dove viene)
  local path = vim.api.nvim_buf_get_name(0)
  local ps = parts(path)
  if #ps == 0 then return vim.notify('Scan Studio: no part here', vim.log.levels.WARN) end
  local row, lines, name = vim.api.nvim_win_get_cursor(0)[1], vim.api.nvim_buf_get_lines(0, 0, -1, false), nil
  for i = row, 1, -1 do
    name = lines[i]:match('^## (.*)')
    if name then break end
  end
  local p = ps[1]
  for _, x in ipairs(ps) do if name and x.name == name then p = x end end
  local text = p.text .. '\n\n' .. cite(p)
  vim.fn.setreg('+', text); vim.fn.setreg('"', text)
  vim.notify(('Scan Studio: copied “%s”'):format(p.name ~= '' and p.name or p.title or ''), vim.log.levels.INFO)
end

function M.insert()
  local all = {}
  for _, path in ipairs(files()) do
    for _, p in ipairs((parts(path))) do
      p.label = ('%s  %s%s  %s'):format(p.date or '', p.title or '', p.name ~= '' and (' · ' .. p.name) or '', (p.text:gsub('%s+', ' ')):sub(1, 60))
      all[#all + 1] = p
    end
  end
  table.sort(all, function(a, b) return a.label > b.label end)
  local put = function(p)
    local lines = vim.split(p.text .. '\n\n' .. cite(p), '\n')
    vim.api.nvim_put(lines, 'l', true, true)
  end
  local ok = pcall(require, 'telescope.pickers')
  if not ok then
    return vim.ui.select(all, { prompt = 'Insert from Scan Studio', format_item = function(p) return p.label end }, function(p) if p then put(p) end end)
  end
  local win = vim.api.nvim_get_current_win()
  local pickers, finders, conf = require('telescope.pickers'), require('telescope.finders'), require('telescope.config').values
  local actions, state, previewers = require('telescope.actions'), require('telescope.actions.state'), require('telescope.previewers')
  pickers.new({}, {
    prompt_title = 'Insert from Scan Studio',
    finder = finders.new_table({ results = all, entry_maker = function(p) return { value = p, display = p.label, ordinal = p.label .. ' ' .. p.text } end }),
    sorter = conf.generic_sorter({}),
    previewer = previewers.new_buffer_previewer({ define_preview = function(self, e)
      vim.api.nvim_buf_set_lines(self.state.bufnr, 0, -1, false, vim.split(e.value.text, '\n'))
      vim.bo[self.state.bufnr].filetype = 'markdown'
    end }),
    attach_mappings = function(buf)
      actions.select_default:replace(function()
        local p = state.get_selected_entry().value
        actions.close(buf)
        vim.api.nvim_set_current_win(win)
        put(p)
      end)
      return true
    end,
  }):find()
end

function M.setup(opts)
  opts = opts or {}
  if opts.dir then M.dir = vim.fn.expand(opts.dir) end
  vim.api.nvim_create_user_command('Scans', M.pick, { desc = 'Scan Studio: open a transcription' })
  vim.api.nvim_create_user_command('ScansGrep', M.grep, { desc = 'Scan Studio: search the transcriptions' })
  vim.api.nvim_create_user_command('ScanTake', M.take, { desc = 'Scan Studio: copy the part under the cursor' })
  vim.api.nvim_create_user_command('ScanInsert', M.insert, { desc = 'Scan Studio: insert a part here, with where it comes from' })
  -- le trascrizioni si leggono, non si scrivono: nello studio si corregge, e la cartella si riscrive
  vim.api.nvim_create_autocmd('BufReadPost', {
    pattern = M.dir .. '/*',
    callback = function(ev)
      vim.bo[ev.buf].readonly = true
      vim.bo[ev.buf].modifiable = false
      vim.bo[ev.buf].autoread = true
    end,
  })
  if opts.keys ~= false then
    vim.keymap.set('n', '<leader>yo', M.pick, { desc = 'Scan Studio: open a transcription' })
    vim.keymap.set('n', '<leader>yg', M.grep, { desc = 'Scan Studio: search the transcriptions' })
    vim.keymap.set('n', '<leader>yt', M.take, { desc = 'Scan Studio: copy this part' })
    vim.keymap.set('n', '<leader>yi', M.insert, { desc = 'Scan Studio: insert a part here' })
  end
  return M
end

return M
