$(document).ready(function() {
    'use strict';

    const themeCookie = 'selected-paragon-theme-variant';

    function applyThemeOnPage(){
      const theme = $.cookie(themeCookie);

      if (theme === 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        $('body').addClass("unity-dark-theme");
        $("#toggle-switch-input").prop("checked", true);
      }
      
      $('body').toggleClass("unity-dark-theme", theme === 'dark');       // append or remove dark-class based on cookie-value
      
      updateAccessibility();
    }

    function setThemeToggleBtnState(){
      const theme = $.cookie(themeCookie);
      $("#toggle-switch-input").prop("checked", theme === 'dark');
      updateAccessibility();
    }

    function updateAccessibility() {
      const theme = $.cookie(themeCookie);
      const textWrapper = $('#theme-label');
      if (theme === 'dark') {
        textWrapper.text('Switch to Light Mode');
        textWrapper.attr('aria-checked', 'true');
      } else {
        textWrapper.text('Switch to Dark Mode');
        textWrapper.attr('aria-checked', 'false');
      }
    }

    // Listener for updating the theme inside an iframe
    window.addEventListener("message", function(e){
      if (e.data && e.data["indigo-toggle-dark"]){
        applyThemeOnPage();
      }
    });

    applyThemeOnPage();  // loading theme on page load
    setThemeToggleBtnState(); // check/uncheck toggle btn based on theme
});