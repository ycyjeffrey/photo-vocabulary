// Chrome serializes this function for isolated-world injection; keep helpers inside it.
export async function fillQuizlet({ title, tsv, cardCount, mode, overwrite }) {
  const fail = (message) => ({ ok: false, message });
  if (location.protocol !== 'https:' || !['quizlet.com', 'www.quizlet.com'].includes(location.hostname) ||
      !/^\/(?:[a-z]{2}(?:-[a-z]{2})?\/)?create-set\/?$/i.test(location.pathname)) {
    return fail('請在已登入的 Quizlet「建立字卡集」頁面使用。');
  }
  if (typeof tsv !== 'string' || !tsv.trim() || tsv.length > 2 * 1024 * 1024 ||
      typeof title !== 'string' || !title.trim() || title.length > 200 ||
      !Number.isInteger(cardCount) || cardCount < 1 || cardCount > 500 ||
      !['auto', 'focused'].includes(mode)) {
    return fail('字卡資料無效，請重新載入 JSON。');
  }
  const rows = tsv.split('\n');
  if (rows.length !== cardCount || rows.some(row => {
    const fields = row.split('\t');
    return fields.length !== 2 || fields.some(field => !field.trim());
  })) {
    return fail('字卡數或 TSV 欄位不一致，請重新載入 JSON。');
  }
  const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
  const visible = element => {
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.visibility !== 'hidden' &&
      style.display !== 'none' && !element.closest('[inert], [aria-hidden="true"]');
  };
  const writable = element => visible(element) && !element.disabled && !element.readOnly &&
    element.getAttribute('aria-disabled') !== 'true';
  const label = element => [
    element.getAttribute('aria-label'), element.getAttribute('placeholder'),
    element.getAttribute('name'), element.getAttribute('data-testid'),
    ...(element.labels ? [...element.labels].map(item => item.textContent) : []),
    ...(element.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean)
      .map(id => document.getElementById(id)?.textContent),
  ].filter(Boolean).join(' ').trim();
  const importPattern = /import|paste|匯入|貼上|导入|粘贴|貼り付け|インポート/i;
  const titlePattern = /title|標題|标题|タイトル/i;
  const value = element => element.isContentEditable ? element.innerText : element.value;
  const setValue = (element, text) => {
    element.focus();
    if (element.isContentEditable) {
      element.textContent = text;
      element.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }));
    } else {
      const prototype = element.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(element, text);
      element.dispatchEvent(new Event('input', { bubbles: true }));
    }
    element.dispatchEvent(new Event('change', { bubbles: true }));
    element.blur();
  };
  const textboxes = () => [...document.querySelectorAll('textarea,[contenteditable="true"][role="textbox"]')]
    .filter(writable);
  const findImport = () => {
    const matches = textboxes().filter(element => importPattern.test(label(element)));
    if (matches.length === 1) return matches[0];
    // Quizlet can label the modal, rather than its text area.
    if (matches.length === 0) {
      const inDialog = textboxes().filter(element => {
        const dialog = element.closest('[role="dialog"],dialog');
        return dialog && importPattern.test(label(dialog));
      });
      if (inDialog.length === 1) return inDialog[0];
    }
    return null;
  };
  const titleFields = [...document.querySelectorAll('input:not([type]),input[type="text"],textarea')]
    .filter(element => writable(element) && titlePattern.test(label(element)));
  const titleField = titleFields.length === 1 ? titleFields[0] : null;
  const focused = document.activeElement;
  let target;
  if (mode === 'focused') {
    if (!(focused instanceof HTMLElement) ||
        !focused.matches('textarea,[contenteditable="true"][role="textbox"]') ||
        !writable(focused) || titlePattern.test(label(focused))) {
      return fail('請先關閉擴充面板，開啟 Quizlet Import，點一下「貼上文字」的大文字框，再開啟擴充功能重試。');
    }
    target = focused;
  } else {
    target = findImport();
    if (!target) {
      if (textboxes().some(element => !titlePattern.test(label(element)))) {
        return fail('頁面已有未辨識的文字框，為避免誤按 Import 確認，不自動點擊。請手動開啟 Import 並點一下貼上框，再使用焦點填入。');
      }
      const triggers = [...document.querySelectorAll('button,[role="button"],a')].filter(element =>
        writable(element) && /^(?:import(?:\s+(?:from|your|text|data).*)?|匯入.*|导入.*|インポート.*)$/i
          .test((element.getAttribute('aria-label') || element.textContent || '').trim()) &&
        !element.closest('[role="dialog"],dialog') &&
        !(element instanceof HTMLButtonElement && element.type === 'submit') &&
        !(element instanceof HTMLAnchorElement && element.getAttribute('href') &&
          !element.getAttribute('href').startsWith('#')));
      if (triggers.length !== 1) {
        return fail('找不到唯一的 Import 入口。請手動開啟 Import、點一下貼上文字框，再選「填入剛才選取的文字框」。未填入任何內容。');
      }
      triggers[0].click();
      for (let attempt = 0; attempt < 30 && !target; attempt++) {
        await wait(100);
        target = findImport();
      }
    }
  }
  if (!target) {
    return fail('Import 已開啟，但無法辨識文字框。請點一下正確文字框，再用「填入剛才選取的文字框」；或複製 TSV 手動貼上。');
  }
  if (titleField && titleField.isConnected && value(titleField).trim() &&
      value(titleField) !== title && !overwrite) {
    return fail('Quizlet 標題已有不同內容。若確定取代，請勾選「允許取代既有標題／匯入文字」。');
  }
  if (value(target).trim() && value(target) !== tsv && !overwrite) {
    return fail('匯入文字框已有不同內容。未覆寫；請確認後勾選「允許取代既有標題／匯入文字」。');
  }
  const existingTitle = titleField?.isConnected && writable(titleField) ? titleField : null;
  if (existingTitle) setValue(existingTitle, title);
  if (!target.isConnected || !writable(target)) {
    return fail('Quizlet 重新載入了表單，請重試。若已填入標題，請保留或自行修改；尚未填入字卡。');
  }
  setValue(target, tsv);
  await wait(350);
  const currentTarget = target.isConnected ? target : findImport();
  const textVerified = currentTarget && value(currentTarget).replace(/\r\n/g, '\n') === tsv;
  const currentTitle = existingTitle?.isConnected ? existingTitle : (
    [...document.querySelectorAll('input,textarea')].filter(element => writable(element) && titlePattern.test(label(element)))
  );
  const titleVerified = existingTitle ? (
    Array.isArray(currentTitle) ? currentTitle.length === 1 && value(currentTitle[0]) === title
      : value(currentTitle) === title
  ) : false;
  if (!textVerified || (existingTitle && !titleVerified)) {
    return fail('填入後讀回不一致，Quizlet 可能沒有接受修改。尚未匯入或建立字卡集；請複製 TSV 手動貼上並核對。');
  }
  return {
    ok: true, cardCount, textVerified: true, titleVerified,
    message: `已填入並讀回核對 ${cardCount} 張字卡的 TSV。` +
      (titleVerified ? '標題已核對。' : '請手動填寫或核對標題。') +
      '尚未匯入或發佈：請選 Tab／換行分隔，核對預覽，手動按 Import，設定語言，最後由你按 Create。',
  };
}
