local ok, builtin = pcall(require, 'telescope.builtin')
if not ok then
    return
end
vim.keymap.set('n', '<leader>pf', builtin.find_files, {})
vim.keymap.set('n', '<leader>pb', builtin.buffers, {})
vim.keymap.set('n', '<C-p>f', builtin.git_files, {})
vim.keymap.set('n', '<leader>pw', function()
	builtin.grep_string()
end)
vim.keymap.set('n', '<leader>ps', function()
	builtin.grep_string({ search = vim.fn.input("Grep > ") })
end)
vim.keymap.set('n', '<leader>vh', builtin.help_tags, {})

