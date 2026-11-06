"""Shared list selection used by the technical and pricing screens."""
import streamlit as st


def button_navigation(options,key):
    if st.session_state.get(key) not in options:st.session_state[key]=options[0]
    def select(value):st.session_state[key]=value
    for column,option in zip(st.columns(len(options)),options):
        column.button(option,key=key+'_'+option,width='stretch',
                      type='primary' if st.session_state[key]==option else 'secondary',
                      on_click=select,args=(option,))
    return st.session_state[key]


def selected_rows(frame,key):
    table=frame.copy().reset_index(drop=True)
    identity=tuple(table.iloc[:,0].astype(str)) if len(table.columns) else ()
    marker=key+'_identity'
    if st.session_state.get(marker)!=identity:
        st.session_state.pop(key,None)
        st.session_state[marker]=identity
    table.insert(0,'Selecionar',False)
    edited=st.data_editor(table,key=key,hide_index=True,width='stretch',
                          disabled=list(frame.columns),
                          column_config={'Selecionar':st.column_config.CheckboxColumn('Selecionar',default=False)})
    return edited.loc[edited['Selecionar']==True,frame.columns]
