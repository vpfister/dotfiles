local ok, theme = pcall(require, 'onedark')
if not ok then
    return
end
theme.setup {
	style = 'darker'
}
theme.load()
